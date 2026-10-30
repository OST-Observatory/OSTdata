"""
Sky view of plate-solved FITS files (Aladin Lite in the frontend): a JPEG preview with the matching
WCS, so Aladin places it on the sky, and the SIMBAD objects inside the field from the run's cached
auxiliary objects (no live SIMBAD query: works during CDS outages).

Image orientation: like the PNG thumbnails, the first FITS row is the top image row; Aladin reads
image row 1 (top) as pixel y = 1, so the solver's WCS only needs to be scaled to the preview size.
"""
from __future__ import annotations

import logging
import warnings
from io import BytesIO
from pathlib import Path

import numpy as np
from django.conf import settings

from obs_run.preview_cache import touch

logger = logging.getLogger(__name__)

DEFAULT_MAX_DIM = 2048
JPEG_QUALITY = 80


def datafile_wcs_header(datafile):
    """FITS WCS keywords of the full image from the plate solution, or None if not solved."""
    def value(name):
        return getattr(datafile, f'wcs_{name}', None)

    if not datafile.plate_solved or value('crval1') is None or value('crval2') is None:
        return None
    if value('crpix1') is None or value('crpix2') is None:
        return None
    width, height = int(datafile.naxis1 or 0), int(datafile.naxis2 or 0)
    if width <= 0 or height <= 0:
        return None
    header = {
        'NAXIS': 2, 'NAXIS1': width, 'NAXIS2': height,
        'CTYPE1': 'RA---TAN', 'CTYPE2': 'DEC--TAN', 'CUNIT1': 'deg', 'CUNIT2': 'deg', 'EQUINOX': 2000.0,
        'CRVAL1': float(value('crval1')), 'CRVAL2': float(value('crval2')),
        'CRPIX1': float(value('crpix1')), 'CRPIX2': float(value('crpix2')),
    }
    cd = [value('cd1_1'), value('cd1_2'), value('cd2_1'), value('cd2_2')]
    if all(v is not None for v in cd):
        header.update({'CD1_1': cd[0], 'CD1_2': cd[1], 'CD2_1': cd[2], 'CD2_2': cd[3]})
    elif value('cdelt1') is not None and value('cdelt2') is not None:
        # CDELT/CROTA form -> CD matrix
        rotation = np.radians(float(value('crota2') or value('crota1') or 0.0))
        cdelt1, cdelt2 = float(value('cdelt1')), float(value('cdelt2'))
        header.update({
            'CD1_1': cdelt1 * np.cos(rotation), 'CD1_2': -cdelt2 * np.sin(rotation),
            'CD2_1': cdelt1 * np.sin(rotation), 'CD2_2': cdelt2 * np.cos(rotation),
        })
    else:
        return None
    return {key: (float(v) if isinstance(v, np.floating) else v) for key, v in header.items()}


def block_factor(width, height, max_dim=DEFAULT_MAX_DIM):
    """Block size averaged before stretching: the image is reduced to >= max_dim first (fast, low noise)."""
    return max(1, max(int(width), int(height)) // max_dim)


def covered_size(width, height, max_dim=DEFAULT_MAX_DIM):
    """Part of the image the preview shows: cropped to whole blocks (at most block-1 pixels at the far edges)."""
    k = block_factor(width, height, max_dim)
    return int(width) // k * k, int(height) // k * k


def scaled_wcs(header, width, height, covered=None):
    """
    WCS of the full image adapted to a preview of width x height pixels showing the first
    covered = (columns, rows) pixels of the image (default: all of it).
    """
    covered_width, covered_height = covered or (header['NAXIS1'], header['NAXIS2'])
    sx = width / covered_width
    sy = height / covered_height
    scaled = dict(header)
    scaled.update({
        'NAXIS1': width, 'NAXIS2': height,
        # Pixel centres: FITS pixel 1 spans 0.5..1.5
        'CRPIX1': (header['CRPIX1'] - 0.5) * sx + 0.5,
        'CRPIX2': (header['CRPIX2'] - 0.5) * sy + 0.5,
        'CD1_1': header['CD1_1'] / sx, 'CD1_2': header['CD1_2'] / sy,
        'CD2_1': header['CD2_1'] / sx, 'CD2_2': header['CD2_2'] / sy,
    })
    return scaled


def _astropy_wcs(header):
    from astropy.wcs import WCS

    return WCS({key: v for key, v in header.items() if key not in ('NAXIS',)}, naxis=2)


def _cache_path(datafile, max_dim):
    base = getattr(settings, 'SER_THUMBNAIL_CACHE_DIR', None) or (Path(settings.BASE_DIR) / 'data' / 'ser_thumbnails')
    digest = (datafile.content_hash or 'nohash').strip() or 'nohash'
    # v2: block-averaged and cropped to whole blocks (the WCS of the payload assumes this)
    return Path(base) / f'df{datafile.pk}_{digest}_sky{max_dim}_v2.jpg'


def render_sky_jpeg(path, max_dim=DEFAULT_MAX_DIM):
    """JPEG preview with the stretch of the FITS thumbnails (ZScale + asinh)."""
    from astropy.io import fits
    from astropy.visualization import AsinhStretch, ImageNormalize, ZScaleInterval
    from PIL import Image

    from obs_run.ser_thumbnails import check_frame_pixels

    with fits.open(str(path), memmap=False) as hdul:
        data = next((np.asarray(hdu.data) for hdu in hdul
                     if getattr(hdu, 'data', None) is not None and np.asarray(hdu.data).ndim >= 2), None)
    if data is None:
        raise ValueError('No image data')
    if data.ndim > 2:
        data = data[0]
    height, width = data.shape
    check_frame_pixels(int(width), int(height))
    # Average k x k blocks before stretching: the full-resolution stretch took ~1.4 s and ~770 MB
    # for a 6252 x 4176 frame, on the reduced image it is a fraction of that (and less noisy)
    k = block_factor(width, height, max_dim)
    covered_width, covered_height = covered_size(width, height, max_dim)
    data = np.asarray(data[:covered_height, :covered_width], dtype=np.float32)
    if k > 1:
        blocks = data.reshape(covered_height // k, k, covered_width // k, k)
        if np.isfinite(data).all():
            data = blocks.mean(axis=(1, 3))
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)  # blocks without finite pixels -> NaN
                data = np.nanmean(blocks, axis=(1, 3))
    finite = np.isfinite(data)
    if not finite.any():
        raise ValueError('Invalid image data')
    vmin, vmax = ZScaleInterval().get_limits(data[finite])
    scaled = np.clip(ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch())(np.where(finite, data, vmin)), 0, 1)
    img = Image.fromarray((scaled * 255.0).astype(np.uint8), mode='L')
    img.thumbnail((max_dim, max_dim))
    buf = BytesIO()
    img.save(buf, format='JPEG', quality=JPEG_QUALITY)
    return buf.getvalue()


def get_sky_jpeg(datafile, path, max_dim=DEFAULT_MAX_DIM):
    """Cached sky JPEG (invalidated when the file or its hash changes)."""
    cache_path = _cache_path(datafile, max_dim)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if cache_path.is_file() and cache_path.stat().st_mtime >= Path(path).stat().st_mtime:
            data = cache_path.read_bytes()
            touch(cache_path)  # last use, for the optional cache cleanup
            return data
    except OSError:
        pass
    jpeg = render_sky_jpeg(path, max_dim)
    try:
        cache_path.write_bytes(jpeg)
    except OSError:
        logger.warning('Could not write sky image cache %s', cache_path, exc_info=True)
    return jpeg


def _inside(wcs, header, ra, dec):
    try:
        x, y = wcs.all_world2pix([[float(ra), float(dec)]], 1)[0]
    except Exception:
        return False
    return 0.5 <= x <= header['NAXIS1'] + 0.5 and 0.5 <= y <= header['NAXIS2'] + 0.5


def sky_objects(datafile, header):
    """Cached SIMBAD objects of the run inside the image, and the objects the file is assigned to."""
    wcs = _astropy_wcs(header)
    objects = []
    seen = set()
    for obj in datafile.object_set.all():
        if obj.ra in (None, -1) or obj.dec in (None, -1) or not _inside(wcs, header, obj.ra, obj.dec):
            continue
        seen.add(obj.name.strip().lower())
        objects.append({
            'name': obj.name, 'ra': obj.ra, 'dec': obj.dec, 'object_type': obj.object_type,
            'v_mag': None, 'main': True, 'object_id': obj.pk,
        })
    run = datafile.observation_run
    for item in (getattr(run, 'aux_objects', None) or []):
        name = str(item.get('name') or '').strip()
        ra, dec = item.get('ra'), item.get('dec')
        if not name or ra is None or dec is None or name.lower() in seen:
            continue
        if not _inside(wcs, header, ra, dec):
            continue
        seen.add(name.lower())
        objects.append({
            'name': name, 'ra': ra, 'dec': dec, 'object_type': item.get('object_type'),
            'object_type_display': item.get('object_type_display'), 'v_mag': item.get('v_mag'),
            'main': False,
        })
    return objects


def prerender_sky_image(datafile):
    """
    Render the sky view image right after a new plate solution, so opening the sky view does not have
    to read the (possibly network-mounted) FITS file. Older solved files are rendered on demand.
    """
    if not getattr(settings, 'SKY_VIEW_PRERENDER', True) or datafile_wcs_header(datafile) is None:
        return False
    try:
        get_sky_jpeg(datafile, Path(str(datafile.datafile)))
        return True
    except Exception:
        logger.warning('Sky image pre-rendering failed for datafile %s', datafile.pk, exc_info=True)
        return False


def sky_view_payload(datafile, path, max_dim=DEFAULT_MAX_DIM):
    """Data for the frontend sky view; {'available': False, 'reason': ...} if not possible."""
    from PIL import Image

    header = datafile_wcs_header(datafile)
    if header is None:
        return {'available': False, 'reason': 'File is not plate-solved'}
    # The WCS must match the JPEG exactly: take the size of the (cached) rendered image
    with Image.open(BytesIO(get_sky_jpeg(datafile, path, max_dim))) as img:
        width, height = img.size
    covered = covered_size(header['NAXIS1'], header['NAXIS2'], max_dim)
    center = _astropy_wcs(header).all_pix2world([[(header['NAXIS1'] + 1) / 2, (header['NAXIS2'] + 1) / 2]], 1)[0]
    field = max(abs(header['CD1_1']) + abs(header['CD1_2']), abs(header['CD2_1']) + abs(header['CD2_2'])) * \
        max(header['NAXIS1'], header['NAXIS2'])
    run = datafile.observation_run
    return {
        'available': True,
        'wcs': scaled_wcs(header, width, height, covered),
        # Versioned image URL parameter: the browser may cache the image for good
        'image_version': f"{(datafile.content_hash or 'nohash')[:16]}-{max_dim}-v2",
        'center': {'ra': float(center[0]), 'dec': float(center[1])},
        'fov_deg': float(field),
        'objects': sky_objects(datafile, header),
        'aux_objects_status': getattr(run, 'aux_objects_status', None),
    }
