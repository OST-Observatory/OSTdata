"""Build WCS from DataFile metadata and filter sky positions to the chip footprint."""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS

if TYPE_CHECKING:
    from obs_run.models import DataFile

logger = logging.getLogger(__name__)


def _finite_coord(val) -> bool:
    try:
        if val is None:
            return False
        f = float(val)
        return np.isfinite(f) and f != -1
    except (TypeError, ValueError):
        return False


def datafile_image_axes(data_file: DataFile) -> tuple[int, int] | None:
    naxis1 = float(data_file.naxis1 or 0)
    naxis2 = float(data_file.naxis2 or 0)
    if naxis1 > 0 and naxis2 > 0:
        return int(naxis1), int(naxis2)
    return None


def has_plate_solve_wcs(data_file: DataFile) -> bool:
    if not data_file.plate_solved:
        return False
    if datafile_image_axes(data_file) is None:
        return False
    return all(
        _finite_coord(getattr(data_file, name))
        for name in ('wcs_crval1', 'wcs_crval2', 'wcs_crpix1', 'wcs_crpix2')
    )


def _has_cd_matrix(data_file: DataFile) -> bool:
    return all(
        _finite_coord(getattr(data_file, f'wcs_cd{i}_{j}'))
        for i in (1, 2)
        for j in (1, 2)
    )


def _has_cdelt(data_file: DataFile) -> bool:
    return _finite_coord(data_file.wcs_cdelt1) and _finite_coord(data_file.wcs_cdelt2)


def _field_center_radec(data_file: DataFile) -> tuple[float, float]:
    if has_plate_solve_wcs(data_file):
        return float(data_file.wcs_crval1), float(data_file.wcs_crval2)
    if (
        data_file.plate_solved
        and _finite_coord(data_file.wcs_ra)
        and _finite_coord(data_file.wcs_dec)
    ):
        return float(data_file.wcs_ra), float(data_file.wcs_dec)
    if _finite_coord(data_file.ra) and _finite_coord(data_file.dec):
        return float(data_file.ra), float(data_file.dec)
    raise ValueError('DataFile has no usable field center')


def _resolve_fov_xy_deg(data_file: DataFile) -> tuple[float, float] | None:
    fov_x = float(data_file.fov_x or 0)
    fov_y = float(data_file.fov_y or 0)
    if fov_x > 0 and fov_y > 0:
        return fov_x, fov_y

    w = data_file.wcs_field_width
    h = data_file.wcs_field_height
    if w and h and float(w) > 0 and float(h) > 0:
        return float(w), float(h)

    if data_file.wcs_field_radius and float(data_file.wcs_field_radius) > 0:
        diameter = float(data_file.wcs_field_radius) * 2.0
        return diameter, diameter

    pixel_size = data_file.pixel_size
    focal_length = data_file.focal_length
    naxis1 = data_file.naxis1
    naxis2 = data_file.naxis2
    if not (
        pixel_size and float(pixel_size) > 0
        and focal_length and float(focal_length) > 0
        and naxis1 and float(naxis1) > 0
        and naxis2 and float(naxis2) > 0
    ):
        return None

    pixel_size_mm = float(pixel_size) / 1000.0
    focal_length_mm = float(focal_length)
    d = float(naxis1) * pixel_size_mm
    h_mm = float(naxis2) * pixel_size_mm
    double_focal_len = 2.0 * focal_length_mm
    if double_focal_len <= 0:
        return None
    fov_x_deg = 2.0 * math.atan(d / double_focal_len) * 180.0 / math.pi
    fov_y_deg = 2.0 * math.atan(h_mm / double_focal_len) * 180.0 / math.pi
    if 0.001 <= fov_x_deg <= 180.0 and 0.001 <= fov_y_deg <= 180.0:
        return fov_x_deg, fov_y_deg
    return None


def _build_synthetic_wcs(data_file: DataFile, naxis1: int, naxis2: int) -> tuple[WCS, int, int] | None:
    try:
        crval1, crval2 = _field_center_radec(data_file)
    except ValueError:
        return None

    fov = _resolve_fov_xy_deg(data_file)
    if not fov:
        return None
    fov_x, fov_y = fov

    header = {
        'NAXIS': 2,
        'NAXIS1': naxis1,
        'NAXIS2': naxis2,
        'WCSAXES': 2,
        'CTYPE1': 'RA---TAN',
        'CTYPE2': 'DEC--TAN',
        'CUNIT1': 'deg',
        'CUNIT2': 'deg',
        'CRPIX1': naxis1 / 2.0,
        'CRPIX2': naxis2 / 2.0,
        'CRVAL1': crval1,
        'CRVAL2': crval2,
        'CDELT1': fov_x / naxis1,
        'CDELT2': fov_y / naxis2,
    }
    try:
        return WCS(header), naxis1, naxis2
    except Exception as exc:
        logger.warning('Synthetic WCS build failed for DataFile %s: %s', data_file.pk, exc)
        return None


def _build_plate_solve_wcs(data_file: DataFile, naxis1: int, naxis2: int) -> tuple[WCS, int, int] | None:
    header = {
        'NAXIS': 2,
        'NAXIS1': naxis1,
        'NAXIS2': naxis2,
        'WCSAXES': 2,
        'CTYPE1': 'RA---TAN',
        'CTYPE2': 'DEC--TAN',
        'CUNIT1': 'deg',
        'CUNIT2': 'deg',
        'CRVAL1': float(data_file.wcs_crval1),
        'CRVAL2': float(data_file.wcs_crval2),
        'CRPIX1': float(data_file.wcs_crpix1),
        'CRPIX2': float(data_file.wcs_crpix2),
    }
    if _has_cd_matrix(data_file):
        for i in (1, 2):
            for j in (1, 2):
                header[f'CD{i}_{j}'] = float(getattr(data_file, f'wcs_cd{i}_{j}'))
    elif _has_cdelt(data_file):
        header['CDELT1'] = float(data_file.wcs_cdelt1)
        header['CDELT2'] = float(data_file.wcs_cdelt2)
        if _finite_coord(data_file.wcs_crota1):
            header['CROTA1'] = float(data_file.wcs_crota1)
        if _finite_coord(data_file.wcs_crota2):
            header['CROTA2'] = float(data_file.wcs_crota2)
    elif _finite_coord(data_file.wcs_pix_scale):
        # Watney reports arcsec/pixel.
        scale_deg = abs(float(data_file.wcs_pix_scale)) / 3600.0
        header['CDELT1'] = -scale_deg
        header['CDELT2'] = scale_deg
    else:
        return _build_synthetic_wcs(data_file, naxis1, naxis2)

    try:
        return WCS(header), naxis1, naxis2
    except Exception as exc:
        logger.warning('Plate-solve WCS build failed for DataFile %s: %s', data_file.pk, exc)
        return _build_synthetic_wcs(data_file, naxis1, naxis2)


def build_wcs_from_datafile(data_file: DataFile) -> tuple[WCS, int, int] | None:
    """
    Build an astropy WCS for a DataFile.

    Prefers plate-solve WCS (CD/CRPIX/CRVAL) when available, otherwise a
    synthetic TAN WCS from field center and FOV/chip geometry.
    """
    axes = datafile_image_axes(data_file)
    if axes is None:
        return None
    naxis1, naxis2 = axes

    if has_plate_solve_wcs(data_file):
        return _build_plate_solve_wcs(data_file, naxis1, naxis2)
    return _build_synthetic_wcs(data_file, naxis1, naxis2)


def coords_inside_footprint(
    ra_deg,
    dec_deg,
    wcs_obj: WCS,
    naxis1: int,
    naxis2: int,
) -> np.ndarray:
    """Return boolean mask for sky positions that project inside the image bounds."""
    ra_arr = np.atleast_1d(np.asarray(ra_deg, dtype=float))
    dec_arr = np.atleast_1d(np.asarray(dec_deg, dtype=float))
    coord = SkyCoord(ra=ra_arr * u.deg, dec=dec_arr * u.deg)
    x, y = wcs_obj.world_to_pixel(coord)
    finite = np.isfinite(x) & np.isfinite(y)
    inside = (x >= 0) & (x < naxis1) & (y >= 0) & (y < naxis2)
    return finite & inside


def filter_table_to_footprint(result_table, data_file: DataFile):
    """Keep only SIMBAD rows whose coordinates fall on the camera chip."""
    if result_table is None or len(result_table) == 0:
        return result_table

    built = build_wcs_from_datafile(data_file)
    if built is None:
        return result_table

    wcs_obj, naxis1, naxis2 = built
    ras = []
    decs = []
    for row in result_table:
        if 'ra' in result_table.colnames:
            ra_val = row['ra']
            dec_val = row['dec']
        elif 'RA_d' in result_table.colnames:
            ra_val = row['RA_d']
            dec_val = row['DEC_d']
        else:
            ra_val = row[1]
            dec_val = row[2]
        ras.append(float(ra_val))
        decs.append(float(dec_val))

    mask = coords_inside_footprint(ras, decs, wcs_obj, naxis1, naxis2)
    return result_table[mask]
