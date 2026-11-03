"""
ASTAP plate solver (https://www.hnsky.org/astap.htm), command line version astap_cli.

Approach from ost_photometry_package (src/ost_photometry/wcs.py), where it proved itself:

- Archive files are never modified: ASTAP runs in a temporary directory without -update; -o puts its
  .ini/.wcs output there, the solution is read from the .wcs file (-wcs: FITS header format).
- Raw unsigned 16-bit (or 8-bit) files are only linked into the directory. Float data, NaN or negative
  values (stacks, calibrated frames) get a 16-bit copy without the old WCS: ASTAP finds no stars in
  float data. The copy is stretched linearly first, asinh as fallback (linear fails for deep stacks
  whose sky noise ends up at 1-2 ADU, asinh for frames with very poor seeing).
- Approximate coordinates from the header: search radius PLATE_SOLVING_NEARBY_SEARCH_RADIUS (pointing
  can be off by several degrees), otherwise blind (-r 180). -fov is the image height in degrees.
- "No solution" is retried with fewer image stars (-s 100, -s 50): fields with many stars fainter than
  the star database otherwise fail.
- Solutions are checked before use: equal scale and rotation of both axes, corners at distinct sky
  positions, pixel scale close to the one expected from the header.

The WCS refers to the FITS data array like any FITS WCS (pixel y = 1 is the first row), the same
convention as the Watney solutions stored in the archive (see obs_run/sky_view.py).
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from django.conf import settings

from obs_run.plate_solving import PlateSolver, SolverSetupError

logger = logging.getLogger(__name__)

BLIND_RADIUS_DEG = 180
FALLBACK_MAX_STARS = (100, 50)
STRETCHES = ('linear', 'asinh')
UINT16_TOP = 60000
FITS_SUFFIXES = ('fits', 'fit', 'fts')

# Plausibility of a solution
MAX_AXIS_SCALE_DIFF = 0.01      # relative difference of the pixel scales of both axes
MAX_AXIS_ROTATION_DIFF = 0.5    # degrees between the rotation of both axes
MAX_SCALE_DEVIATION = 0.2       # relative deviation from the scale expected from the header
MIN_CORNER_SEPARATION = 30.0    # arcsec between opposite image corners

EXIT_CODES = {
    1: 'no solution found',
    2: 'not enough stars detected',
    16: 'error reading the image file',
    32: 'no star database found',
    33: 'error reading the star database',
    34: 'error updating the input file',
}

_WCS_KEY_PATTERN = re.compile(
    r'^(CTYPE|CRVAL|CRPIX|CDELT|CROTA|CUNIT|PC\d|CD\d|PV\d|[AB]P?_|RADESYS|EQUINOX|LONPOLE|LATPOLE|'
    r'WCSAXES|WCSNAME|PLTSOLVD)'
)


class AstapError(RuntimeError):
    """ASTAP found no (plausible) solution; the message says why."""


def _strip_wcs(header):
    for key in [k for k in header.keys() if _WCS_KEY_PATTERN.match(k)]:
        del header[key]
    return header


def _image_hdu(hdul):
    """First HDU with 2D (or 3D colour) image data."""
    for hdu in hdul:
        if hdu.is_image and hdu.header.get('NAXIS', 0) >= 2 and hdu.header.get('NAXIS1') and hdu.header.get('NAXIS2'):
            return hdu
    return None


def _robust_peak(data):
    """
    Bright end for the stretch: the largest 3x3 median among the 2000 brightest pixels. Single hot or
    dead pixels (e.g. masked values of 1e9) would otherwise push all stars down to a few ADU; a
    percentile would flatten the cores of the bright stars ASTAP builds its quads from.
    """
    finite = np.where(np.isfinite(data), data, -np.inf)
    count = min(2000, finite.size)
    brightest = np.argpartition(finite.ravel(), -count)[-count:]
    rows, cols = np.unravel_index(brightest, finite.shape)
    peak = -np.inf
    for row, col in zip(rows, cols):
        box = finite[max(row - 1, 0):row + 2, max(col - 1, 0):col + 2]
        peak = max(peak, float(np.median(box)))
    return peak


def _stretch_linear(data):
    positive = data[np.isfinite(data) & (data > 0)]
    sky = float(np.percentile(positive, 5)) if positive.size else 0.0
    span = max(_robust_peak(data) - sky, 1e-12)
    scaled = np.clip((np.nan_to_num(data, nan=sky) - sky) / span, 0, 1)
    return (scaled * UINT16_TOP).astype(np.uint16)


def _stretch_asinh(data):
    finite = data[np.isfinite(data)]
    sky = float(np.median(finite))
    sigma = max(1.4826 * float(np.median(np.abs(finite - sky))), 1e-12)
    soft = 3 * sigma
    low = math.asinh(-5 * sigma / soft)
    top = max(math.asinh((_robust_peak(data) - sky) / soft), low + 1e-12)
    values = np.arcsinh((np.nan_to_num(data, nan=sky) - sky) / soft)
    scaled = np.clip((values - low) / (top - low), 0, 1)
    return (scaled * UINT16_TOP).astype(np.uint16)


def _needs_copy(hdu):
    """True if ASTAP cannot use the file as it is (not unsigned 8/16-bit integer data in the primary HDU)."""
    header = hdu.header
    bitpix = header.get('BITPIX')
    if bitpix == 8:
        return False
    if bitpix == 16 and header.get('BZERO', 0) == 32768 and header.get('BSCALE', 1) == 1:
        return False
    if bitpix == 16:
        # Signed 16-bit: usable unless there are negative values
        return bool(np.nanmin(hdu.data) < 0)
    return True


def _write_copy(data, header, target, stretch):
    """16-bit copy of float/signed image data (2D, or the mean of a colour cube) without the old WCS."""
    from astropy.io import fits

    stretched = _stretch_linear(data) if stretch == 'linear' else _stretch_asinh(data)
    header = _strip_wcs(header.copy())
    for key in ('BZERO', 'BSCALE', 'BLANK', 'NAXIS3', 'EXTEND', 'XTENSION', 'PCOUNT', 'GCOUNT'):
        header.remove(key, ignore_missing=True)
    header['HISTORY'] = f'OST data archive: {stretch} 16-bit copy for ASTAP plate solving'
    fits.PrimaryHDU(stretched, header=header).writeto(target, overwrite=True)


def _read_ini(path):
    values = {}
    try:
        for line in Path(path).read_text(errors='replace').splitlines():
            key, sep, value = line.partition('=')
            if sep:
                values[key.strip().upper()] = value.strip()
    except OSError:
        pass
    return values


def _read_wcs_header(path):
    """The .wcs file: FITS header (with -wcs) or the text style of older versions."""
    from astropy.io import fits

    raw = Path(path).read_bytes().decode('ascii', errors='replace')
    if '\n' in raw:
        return fits.Header.fromstring(raw, sep='\n')
    return fits.Header.fromstring(raw)


def _sexagesimal(value, hours):
    total = abs(value) / 15.0 if hours else abs(value)
    degrees = int(total)
    minutes = int((total - degrees) * 60)
    seconds = (total - degrees - minutes / 60) * 3600
    if round(seconds, 2 if hours else 1) >= 60:
        seconds = 0.0
        minutes += 1
        if minutes == 60:
            minutes, degrees = 0, degrees + 1
    if hours:
        return f'{degrees % 24:02d}:{minutes:02d}:{seconds:05.2f}'
    sign = '-' if value < 0 else '+'
    return f'{sign}{degrees:02d}:{minutes:02d}:{seconds:04.1f}'


def solution_from_header(header, naxis1, naxis2, expected_scale=None):
    """
    Solution dict in the keys of solve_and_update_datafile (Watney's JSON names) from the WCS of a
    .wcs header; raises AstapError for implausible solutions.
    """
    from astropy.wcs import WCS

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        wcs = WCS(header, naxis=2)
    if not wcs.has_celestial:
        raise AstapError('solution has no celestial WCS')
    cd = wcs.wcs.cd if wcs.wcs.has_cd() else wcs.pixel_scale_matrix
    cd = np.asarray(cd, dtype=float)

    # Both axes must have the same scale and rotation (skewed solutions are wrong matches)
    scale_x = math.hypot(cd[0, 0], cd[1, 0])
    scale_y = math.hypot(cd[0, 1], cd[1, 1])
    if not scale_x or not scale_y:
        raise AstapError('degenerate solution (zero pixel scale)')
    if abs(scale_x / scale_y - 1) > MAX_AXIS_SCALE_DIFF:
        raise AstapError(f'solution rejected: axis scales differ ({scale_x * 3600:.4f}" vs {scale_y * 3600:.4f}")')
    det = cd[0, 0] * cd[1, 1] - cd[0, 1] * cd[1, 0]
    parity_sign = -1.0 if det < 0 else 1.0
    # Rotation of each axis (equal for a pure rotation + scale, with or without mirroring)
    rot_x = math.degrees(math.atan2(cd[1, 0], parity_sign * cd[0, 0]))
    rot_y = math.degrees(math.atan2(-parity_sign * cd[0, 1], cd[1, 1]))
    rot_diff = abs((rot_x - rot_y + 180) % 360 - 180)
    if rot_diff > MAX_AXIS_ROTATION_DIFF:
        raise AstapError(f'solution rejected: axis rotations differ by {rot_diff:.2f} deg')

    pix_scale = math.sqrt(abs(det)) * 3600.0
    if expected_scale and abs(pix_scale / expected_scale - 1) > MAX_SCALE_DEVIATION:
        raise AstapError(
            f'solution rejected: pixel scale {pix_scale:.3f}"/px, expected {expected_scale:.3f}"/px from the header'
        )

    corners = wcs.all_pix2world([[1, 1], [naxis1, naxis2]], 1)
    if _separation_arcsec(corners[0], corners[1]) < MIN_CORNER_SEPARATION:
        raise AstapError('degenerate solution (image corners at the same sky position)')

    ra, dec = (float(v) for v in wcs.all_pix2world([[(naxis1 + 1) / 2, (naxis2 + 1) / 2]], 1)[0])
    ra %= 360.0
    width = naxis1 * pix_scale / 3600.0
    height = naxis2 * pix_scale / 3600.0

    def card(name):
        value = header.get(name)
        return float(value) if isinstance(value, (int, float)) else None

    return {
        'success': True,
        'ra': ra,
        'dec': dec,
        'ra_hms': _sexagesimal(ra, hours=True),
        'dec_dms': _sexagesimal(dec, hours=False),
        'fieldRadius': math.hypot(width, height) / 2.0,
        'orientation': card('CROTA2') if card('CROTA2') is not None else rot_y,
        'pixScale': pix_scale,
        'parity': 'normal' if det < 0 else 'flipped',
        'fieldWidth': width,
        'fieldHeight': height,
        'fits_cd1_1': float(cd[0, 0]),
        'fits_cd1_2': float(cd[0, 1]),
        'fits_cd2_1': float(cd[1, 0]),
        'fits_cd2_2': float(cd[1, 1]),
        'fits_cdelt1': card('CDELT1'),
        'fits_cdelt2': card('CDELT2'),
        'fits_crota1': card('CROTA1'),
        'fits_crota2': card('CROTA2'),
        'fits_crpix1': float(wcs.wcs.crpix[0]),
        'fits_crpix2': float(wcs.wcs.crpix[1]),
        'fits_crval1': float(wcs.wcs.crval[0]),
        'fits_crval2': float(wcs.wcs.crval[1]),
    }


def _separation_arcsec(a, b):
    ra1, dec1, ra2, dec2 = (math.radians(v) for v in (a[0], a[1], b[0], b[1]))
    cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(ra1 - ra2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) * 3600.0


class AstapSolver(PlateSolver):
    """ASTAP (astap_cli) with the star database configured by ASTAP_DATABASE_DIR / ASTAP_DATABASE."""

    def __init__(self, executable_path: Optional[str] = None):
        self.executable_path = executable_path or getattr(settings, 'ASTAP_PATH', 'astap_cli')
        self.database_dir = getattr(settings, 'ASTAP_DATABASE_DIR', '') or ''
        self.database = getattr(settings, 'ASTAP_DATABASE', '') or ''
        self.call_timeout = int(getattr(settings, 'ASTAP_TIMEOUT_SECONDS', 120))
        # Total time per file and search mode (nearby or blind), over all retries
        self.budget = int(getattr(settings, 'PLATE_SOLVING_TIMEOUT_SECONDS', 600))
        self.work_dir = getattr(settings, 'ASTAP_WORK_DIR', None) or None

    def get_name(self) -> str:
        return 'astap'

    def get_supported_formats(self) -> List[str]:
        return list(getattr(settings, 'ASTAP_SUPPORTED_FORMATS', [*FITS_SUFFIXES, 'tiff', 'tif']))

    def _executable(self):
        path = Path(self.executable_path)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return shutil.which(self.executable_path)

    def is_available(self) -> bool:
        available = self._executable() is not None
        if not available:
            logger.info('ASTAP not available: %s not found', self.executable_path)
        return available

    def _database_dirs(self):
        if self.database_dir:
            return [Path(self.database_dir)]
        executable = self._executable()
        dirs = [Path(executable).resolve().parent] if executable else []
        return dirs + [Path('/opt/astap'), Path('/usr/share/astap'), Path('/usr/local/opt/astap')]

    def installed_databases(self) -> List[str]:
        """Star databases found next to ASTAP or in ASTAP_DATABASE_DIR (e.g. ['d50'])."""
        found = set()
        for directory in self._database_dirs():
            try:
                for entry in directory.iterdir():
                    match = re.match(r'^([a-z]\d\d)_\d{4}\.\d+$', entry.name, re.IGNORECASE)
                    if match:
                        found.add(match.group(1).lower())
            except OSError:
                continue
        return sorted(found)

    def describe(self) -> Dict:
        executable = self._executable()
        info = {'name': self.get_name(), 'available': executable is not None,
                'path': executable or self.executable_path, 'version': None, 'details': ''}
        if not executable:
            info['details'] = 'astap_cli not found (ASTAP_PATH)'
            return info
        try:
            result = subprocess.run([executable, '-h'], capture_output=True, text=True, timeout=10, check=False)
            text = f'{result.stdout}\n{result.stderr}'
            match = re.search(r'version\s*:?\s*([\w.\-]+)', text, re.IGNORECASE)
            info['version'] = match.group(1) if match else None
        except Exception as exc:
            logger.debug('ASTAP version check failed: %s', exc)
        databases = self.installed_databases()
        selected = self.database or 'automatic'
        info['details'] = (
            f"databases: {', '.join(databases) if databases else 'none found (ASTAP_DATABASE_DIR)'}; "
            f'selected: {selected}'
        )
        return info

    # --- solving -------------------------------------------------------------------------------

    def solve(self, image_path: str, min_radius: float, max_radius: float, hints: Optional[Dict] = None) -> Dict:
        return self._solve(image_path, None, None, BLIND_RADIUS_DEG, hints or {})

    def solve_nearby(self, image_path: str, ra_deg: float, dec_deg: float, field_radius: float,
                     search_radius: float, hints: Optional[Dict] = None) -> Optional[Dict]:
        return self._solve(image_path, ra_deg, dec_deg, search_radius, hints or {})

    def _command(self, image, output, radius, fov, ra_deg, dec_deg, max_stars, check_pattern):
        cmd = [self._executable() or self.executable_path, '-f', str(image), '-o', str(output),
               '-r', f'{radius:.10g}', '-fov', f'{fov:.10g}', '-wcs']
        if ra_deg is not None and dec_deg is not None:
            cmd += ['-ra', f'{(ra_deg % 360) / 15:.10g}', '-spd', f'{dec_deg + 90:.10g}']
        if max_stars:
            cmd += ['-s', str(max_stars)]
        if check_pattern:
            cmd += ['-check', 'y']
        if self.database_dir:
            cmd += ['-d', self.database_dir]
        if self.database:
            cmd += ['-D', self.database]
        return cmd

    def _solve(self, image_path, ra_deg, dec_deg, radius, hints):
        from astropy.io import fits

        source = Path(image_path)
        if not source.exists():
            raise FileNotFoundError(f'Image file not found: {image_path}')
        if not self._executable():
            raise SolverSetupError(f'ASTAP executable not found: {self.executable_path}')
        deadline = time.monotonic() + self.budget
        suffix = source.suffix.lstrip('.').lower()
        naxis1, naxis2 = int(hints.get('naxis1') or 0), int(hints.get('naxis2') or 0)
        check_pattern = False
        copy_data = copy_header = None
        if suffix in FITS_SUFFIXES:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                with fits.open(source, memmap=False) as hdul:
                    hdu = _image_hdu(hdul)
                    if hdu is None:
                        raise AstapError('no image data in the FITS file')
                    naxis1, naxis2 = int(hdu.header['NAXIS1']), int(hdu.header['NAXIS2'])
                    if hdu is not hdul[0] or _needs_copy(hdu):
                        copy_data = np.asarray(hdu.data, dtype=np.float32)
                        if copy_data.ndim == 3:
                            # Colour cube (3, height, width): solve on the mean
                            copy_data = np.nanmean(copy_data, axis=0)
                        copy_header = hdu.header.copy()
                    else:
                        # Raw one-shot-colour frames: ASTAP's filter against the Bayer pattern (1x1 binning)
                        binning = int(hdu.header.get('XBINNING', 1) or 1)
                        check_pattern = bool(hdu.header.get('BAYERPAT')) and binning == 1
        if not (naxis1 and naxis2):
            raise AstapError('image size unknown')

        fov_y = float(hints.get('fov_y') or 0)
        # -fov 0: ASTAP derives the field from the header (FOCALLEN, XPIXSZ)
        fov = fov_y if fov_y > 0 else 0.0
        expected_scale = fov_y * 3600.0 / naxis2 if fov_y > 0 else None

        with tempfile.TemporaryDirectory(prefix='astap_', dir=self.work_dir) as tmp:
            tmp = Path(tmp)
            if copy_data is not None:
                variants = STRETCHES
            else:
                # Archive files are only linked: ASTAP reads them, all output goes to the temp directory
                link = tmp / f"image.{'fits' if suffix in FITS_SUFFIXES else suffix}"
                try:
                    link.symlink_to(source.resolve())
                except OSError:
                    shutil.copy2(source, link)
                variants = (None,)

            errors = []
            for stretch in variants:
                image = link if stretch is None else tmp / f'image_{stretch}.fits'
                if stretch is not None:
                    _write_copy(copy_data, copy_header, image, stretch)
                for max_stars in (None, *FALLBACK_MAX_STARS):
                    remaining = deadline - time.monotonic()
                    if remaining < 5:
                        errors.append(f'time budget of {self.budget} s used up')
                        raise AstapError('; '.join(dict.fromkeys(errors)))
                    output = tmp / f"solution_{stretch or 'raw'}_{max_stars or 'all'}"
                    cmd = self._command(image, output, radius, fov, ra_deg, dec_deg, max_stars, check_pattern)
                    logger.debug('Running ASTAP: %s', ' '.join(cmd))
                    call_timeout = min(self.call_timeout, remaining)
                    try:
                        result = subprocess.run(
                            cmd, capture_output=True, text=True, check=False, timeout=call_timeout, cwd=tmp,
                        )
                    except subprocess.TimeoutExpired:
                        errors.append(f'timeout after {int(call_timeout)} s')
                        continue
                    ini = _read_ini(output.with_suffix('.ini'))
                    wcs_file = output.with_suffix('.wcs')
                    solved = result.returncode == 0 and ini.get('PLTSOLVD', 'T').upper().startswith('T')
                    if solved and wcs_file.is_file():
                        try:
                            return solution_from_header(_read_wcs_header(wcs_file), naxis1, naxis2, expected_scale)
                        except AstapError as exc:
                            errors.append(str(exc))
                            continue
                    errors.append(self._failure_reason(result, ini))
                    if result.returncode in (32, 33):
                        # Star database missing/unreadable: a problem of the installation, not of the file
                        raise SolverSetupError('; '.join(dict.fromkeys(errors)))
                    if result.returncode == 16:
                        # Unreadable image: fewer stars or another stretch cannot help
                        raise AstapError('; '.join(dict.fromkeys(errors)))
        raise AstapError('; '.join(dict.fromkeys(errors)) or 'no solution found')

    @staticmethod
    def _failure_reason(result, ini):
        if ini.get('ERROR'):
            return ini['ERROR']
        if result.returncode in EXIT_CODES:
            return EXIT_CODES[result.returncode]
        lines = (result.stderr or result.stdout or '').strip().splitlines()
        return lines[-1] if lines else f'exit code {result.returncode}'
