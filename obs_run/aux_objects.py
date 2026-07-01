"""Compute and cache SIMBAD auxiliary objects for observation runs."""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.coordinates.angles import Angle
from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from objects.models import Object
from obs_run.models import DataFile, ObservationRun
from obs_run.wcs_utils import build_wcs_from_datafile, filter_table_to_footprint
from obs_run.simbad_rate_limit import wait_for_aux_simbad_query_slot
from utilities import (
    _query_region_safe,
    _radius_str_from_arcmin,
    detect_object_type_from_simbad_types,
    get_effective_exposure_type_filter,
)

logger = logging.getLogger(__name__)

OBJECT_TYPE_LABELS = dict(Object.OBJECT_TYPE_CHOICES)


def _pending_stale_seconds() -> int:
    return int(getattr(settings, 'AUX_OBJECTS_PENDING_STALE_SECONDS', 120))


def _row_limit() -> int:
    return int(getattr(settings, 'AUX_OBJECTS_ROW_LIMIT', 100))


def _cluster_separation_deg() -> float:
    """Fallback separation (deg) when field size cannot be estimated from metadata."""
    return float(getattr(settings, 'AUX_OBJECTS_CLUSTER_SEPARATION_DEG', 1.0))


def _cluster_fov_fraction() -> float:
    """Fraction of the smaller field diameter used as same-pointing threshold."""
    return float(getattr(settings, 'AUX_OBJECTS_CLUSTER_FOV_FRACTION', 0.5))


def _cluster_min_separation_deg() -> float:
    """Minimum threshold (deg) so dithered frames within one field still cluster."""
    arcmin = float(getattr(settings, 'AUX_OBJECTS_CLUSTER_MIN_ARCMIN', 2.0))
    return arcmin / 60.0


def _light_fits_filter_q(*, require_plate_solved: bool):
    q = Q(datafile__file_type='FITS') & get_effective_exposure_type_filter('LI', 'datafile__')
    if require_plate_solved:
        return q & Q(
            datafile__plate_solved=True,
            datafile__wcs_ra__isnull=False,
        ) & ~Q(datafile__wcs_ra=-1)
    return q & (
        Q(datafile__plate_solved=True, datafile__wcs_ra__isnull=False)
        | Q(datafile__ra__isnull=False)
    ) & ~Q(datafile__ra=-1)


def mark_aux_objects_pending(run: ObservationRun) -> None:
    run.aux_objects_status = ObservationRun.AUX_STATUS_PENDING
    run.aux_objects_error = ''
    run.aux_objects_started_at = timezone.now()
    run.save(update_fields=['aux_objects_status', 'aux_objects_error', 'aux_objects_started_at'])


def query_runs_for_aux_objects(
    *,
    mode: str = 'missing',
    require_wcs: bool = True,
    force: bool = False,
    run_ids: list[int] | None = None,
):
    """
    Return observation runs eligible for auxiliary-object SIMBAD lookup.

    mode: 'missing' (no successful cache), 'all', or 'selected' (requires run_ids).
    """
    qs = ObservationRun.objects.filter(photometry=True)
    qs = qs.filter(_light_fits_filter_q(require_plate_solved=require_wcs)).distinct()

    if run_ids is not None:
        qs = qs.filter(pk__in=run_ids)

    if mode == 'missing' or (mode == 'all' and not force):
        qs = qs.exclude(
            aux_objects_status=ObservationRun.AUX_STATUS_READY,
            aux_objects_computed_at__isnull=False,
        )
    return qs.order_by('pk')


def query_runs_with_outdated_aux_after_wcs():
    """Runs whose plate-solved WCS is newer than the last aux-objects computation."""
    qs = ObservationRun.objects.filter(photometry=True)
    qs = qs.filter(_light_fits_filter_q(require_plate_solved=True)).distinct()
    qs = qs.filter(aux_objects_computed_at__isnull=False)
    qs = qs.filter(
        datafile__plate_solved=True,
        datafile__plate_solve_attempted_at__gt=F('aux_objects_computed_at'),
    )
    return qs.distinct().order_by('pk')


def should_enqueue_aux_objects_for_run(run: ObservationRun, *, force: bool = False) -> bool:
    if not run.photometry:
        return False
    if not force and run.aux_objects_status == ObservationRun.AUX_STATUS_READY and run.aux_objects_computed_at:
        return False
    if run.aux_objects_status == ObservationRun.AUX_STATUS_PENDING and not pending_is_stale(run):
        return False
    return True


def _light_fits_queryset(run: ObservationRun):
    return DataFile.objects.filter(
        observation_run=run,
        file_type='FITS',
    ).filter(get_effective_exposure_type_filter('LI'))


def get_file_center(data_file: DataFile) -> tuple[float, float]:
    """Return field center RA/Dec in degrees (WCS preferred over header)."""
    if (
        data_file.plate_solved
        and data_file.wcs_ra is not None
        and data_file.wcs_dec is not None
        and data_file.wcs_ra != -1
        and data_file.wcs_dec != -1
    ):
        return float(data_file.wcs_ra), float(data_file.wcs_dec)
    if data_file.ra not in (None, -1) and data_file.dec not in (None, -1):
        return float(data_file.ra), float(data_file.dec)
    raise ValueError('DataFile has no usable coordinates')


def _pick_representative_from_queryset(qs) -> DataFile | None:
    """Pick the best LIGHT FITS from a queryset (or cluster subset)."""
    rep = (
        qs.filter(plate_solved=True, wcs_ra__isnull=False)
        .exclude(wcs_ra=-1)
        .exclude(wcs_dec=-1)
        .order_by('-plate_solve_attempted_at', 'hjd')
        .first()
    )
    if rep:
        return rep

    rep = (
        qs.exclude(ra=-1)
        .exclude(dec=-1)
        .filter(fov_x__gt=0, fov_y__gt=0)
        .order_by('hjd')
        .first()
    )
    if rep:
        return rep

    return qs.exclude(ra=-1).exclude(dec=-1).order_by('hjd').first()


def find_representative_light_fits(run: ObservationRun) -> DataFile | None:
    """Pick a LIGHT FITS file with coordinates and preferably WCS/FOV (whole run)."""
    return _pick_representative_from_queryset(_light_fits_queryset(run))


def _fov_from_chip_and_telescope(data_file: DataFile) -> tuple[float, float] | None:
    """
    Estimate on-sky FOV (deg) from chip geometry and telescope focal length.
    Mirrors the logic in analyze_fits_header when header FOV was not stored.
    """
    pixel_size = data_file.pixel_size
    focal_length = data_file.focal_length
    naxis1 = data_file.naxis1
    naxis2 = data_file.naxis2
    if not (
        pixel_size is not None and pixel_size > 0
        and focal_length is not None and focal_length > 0
        and naxis1 is not None and naxis1 > 0
        and naxis2 is not None and naxis2 > 0
    ):
        return None

    pixel_size_mm = float(pixel_size) / 1000.0
    focal_length_mm = float(focal_length)
    d = float(naxis1) * pixel_size_mm
    h = float(naxis2) * pixel_size_mm
    double_focal_len = 2.0 * focal_length_mm
    if double_focal_len <= 0:
        return None

    fov_x_rad = 2.0 * math.atan(d / double_focal_len)
    fov_y_rad = 2.0 * math.atan(h / double_focal_len)
    fov_x_deg = fov_x_rad * 180.0 / math.pi
    fov_y_deg = fov_y_rad * 180.0 / math.pi
    if not (0.001 <= fov_x_deg <= 180.0 and 0.001 <= fov_y_deg <= 180.0):
        return None
    return fov_x_deg, fov_y_deg


def _field_diameter_deg(data_file: DataFile) -> float | None:
    """
    Estimate angular field diameter (deg) from stored FOV, plate-solve WCS, or chip/telescope.
    """
    fov_x = float(data_file.fov_x or 0)
    fov_y = float(data_file.fov_y or 0)
    if fov_x > 0 and fov_y > 0:
        return math.sqrt(fov_x ** 2 + fov_y ** 2)

    w = data_file.wcs_field_width
    h = data_file.wcs_field_height
    if w and h and float(w) > 0 and float(h) > 0:
        return math.sqrt(float(w) ** 2 + float(h) ** 2)

    if data_file.wcs_field_radius and float(data_file.wcs_field_radius) > 0:
        return float(data_file.wcs_field_radius) * 2.0

    chip_fov = _fov_from_chip_and_telescope(data_file)
    if chip_fov:
        fx, fy = chip_fov
        return math.sqrt(fx ** 2 + fy ** 2)

    return None


def _pair_cluster_threshold_deg(file_a: DataFile, file_b: DataFile) -> float:
    """
    Separation threshold for grouping two frames into the same pointing cluster.

    Primary: fraction of the smaller estimated field diameter (from FOV metadata,
    WCS plate solve, or chip size × pixel scale × focal length).
    Fallback: AUX_OBJECTS_CLUSTER_SEPARATION_DEG when field size is unknown.
    """
    diam_a = _field_diameter_deg(file_a)
    diam_b = _field_diameter_deg(file_b)
    if diam_a is not None and diam_b is not None:
        return max(_cluster_min_separation_deg(), _cluster_fov_fraction() * min(diam_a, diam_b))
    if diam_a is not None or diam_b is not None:
        return max(_cluster_min_separation_deg(), _cluster_fov_fraction() * (diam_a or diam_b))
    return _cluster_separation_deg()


def cluster_light_fits_by_pointing(files: list[DataFile]) -> list[list[DataFile]]:
    """
    Group LIGHT FITS files into pointing clusters by center coordinate proximity.
    Single-linkage: frames chain into one cluster when each step is within threshold.
    """
    indexed: list[tuple[DataFile, float, float]] = []
    for data_file in files:
        try:
            ra, dec = get_file_center(data_file)
        except ValueError:
            continue
        indexed.append((data_file, ra, dec))

    if not indexed:
        return []

    assigned = [False] * len(indexed)
    clusters: list[list[DataFile]] = []

    for i in range(len(indexed)):
        if assigned[i]:
            continue
        cluster_indices = [i]
        assigned[i] = True
        queue = [i]
        while queue:
            ci = queue.pop()
            file_a, ra_a, dec_a = indexed[ci]
            coord_a = SkyCoord(ra_a * u.deg, dec_a * u.deg, frame='icrs')
            for j in range(len(indexed)):
                if assigned[j]:
                    continue
                file_b, ra_b, dec_b = indexed[j]
                coord_b = SkyCoord(ra_b * u.deg, dec_b * u.deg, frame='icrs')
                separation_deg = float(coord_a.separation(coord_b).degree)
                if separation_deg <= _pair_cluster_threshold_deg(file_a, file_b):
                    assigned[j] = True
                    cluster_indices.append(j)
                    queue.append(j)
        clusters.append([indexed[k][0] for k in cluster_indices])

    clusters.sort(key=lambda cluster: get_file_center(cluster[0])[1])
    return clusters


def iter_pointing_clusters(run: ObservationRun) -> list[list[DataFile]]:
    """Return pointing clusters for all usable LIGHT FITS in a run."""
    files = list(_light_fits_queryset(run))
    return cluster_light_fits_by_pointing(files)


def _dedupe_aux_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate SIMBAD objects (same name) across pointing clusters."""
    best_by_name: dict[str, dict[str, Any]] = {}
    for obj in objects:
        key = (obj.get('name') or '').strip().upper()
        if not key:
            key = f"{obj.get('ra')}:{obj.get('dec')}"
        existing = best_by_name.get(key)
        if existing is None:
            best_by_name[key] = obj
            continue
        # Prefer the entry with smaller separation to its field center.
        if obj.get('separation_arcmin', 9999) < existing.get('separation_arcmin', 9999):
            cluster_ids = sorted(set(existing.get('cluster_ids', [])) | set(obj.get('cluster_ids', [])))
            obj = {**obj, 'cluster_ids': cluster_ids}
            best_by_name[key] = obj
        else:
            existing['cluster_ids'] = sorted(
                set(existing.get('cluster_ids', [])) | set(obj.get('cluster_ids', []))
            )
    merged = list(best_by_name.values())
    merged.sort(
        key=lambda item: (
            min(item.get('cluster_ids') or [0]),
            item.get('separation_arcmin', 9999),
            item.get('v_mag') is None,
            item.get('v_mag') or 99,
        )
    )
    return merged


def get_lookup_center_and_fov(data_file: DataFile) -> tuple[float, float, float, float, float]:
    """Return center RA/Dec (deg), FOV width/height (deg), and search radius (deg)."""
    if (
        data_file.plate_solved
        and data_file.wcs_ra is not None
        and data_file.wcs_dec is not None
        and data_file.wcs_ra != -1
        and data_file.wcs_dec != -1
    ):
        ra = float(data_file.wcs_ra)
        dec = float(data_file.wcs_dec)
    elif data_file.ra not in (None, -1) and data_file.dec not in (None, -1):
        ra = float(data_file.ra)
        dec = float(data_file.dec)
    else:
        raise ValueError('Representative LIGHT FITS has no usable coordinates')

    fov_x = float(data_file.fov_x or 0)
    fov_y = float(data_file.fov_y or 0)
    if fov_x <= 0 or fov_y <= 0:
        w = data_file.wcs_field_width
        h = data_file.wcs_field_height
        if w and h and float(w) > 0 and float(h) > 0:
            fov_x = float(w)
            fov_y = float(h)
        elif data_file.wcs_field_radius and float(data_file.wcs_field_radius) > 0:
            diameter = float(data_file.wcs_field_radius) * 2.0
            fov_x = fov_y = diameter
        else:
            default_arcmin = 10.0
            fov_x = fov_y = default_arcmin / 60.0

    radius_deg = math.sqrt(fov_x ** 2 + fov_y ** 2) / 2.0
    return ra, dec, fov_x, fov_y, radius_deg


def _main_target_names_and_coords(run: ObservationRun) -> tuple[set[str], list[tuple[float, float]]]:
    names: set[str] = set()
    coords: list[tuple[float, float]] = []
    for obj in Object.objects.filter(observation_run=run, is_main=True).only('name', 'ra', 'dec'):
        if obj.name:
            names.add(obj.name.strip().upper())
        if obj.ra not in (None, -1) and obj.dec not in (None, -1):
            coords.append((float(obj.ra), float(obj.dec)))
    return names, coords


def _matches_main_target(
    name: str,
    ra: float,
    dec: float,
    main_names: set[str],
    main_coords: list[tuple[float, float]],
    *,
    separation_arcmin: float = 2.0,
) -> bool:
    upper = (name or '').strip().upper()
    if upper and upper in main_names:
        return True
    if not main_coords:
        return False
    obj_coord = SkyCoord(ra * u.deg, dec * u.deg, frame='icrs')
    for m_ra, m_dec in main_coords:
        main_coord = SkyCoord(m_ra * u.deg, m_dec * u.deg, frame='icrs')
        if obj_coord.separation(main_coord).arcminute <= separation_arcmin:
            return True
    return False


def _row_name(row) -> str:
    for key in ('main_id', 'MAIN_ID', 'id', 'ID'):
        if key in row.colnames and row[key] is not None:
            return str(row[key]).strip()
    return str(row[0]).strip()


def _row_ra_dec(row) -> tuple[float, float]:
    if 'ra' in row.colnames:
        ra_val = row['ra']
    elif 'RA_d' in row.colnames:
        ra_val = row['RA_d']
    else:
        ra_val = row[1]
    if 'dec' in row.colnames:
        dec_val = row['dec']
    elif 'DEC_d' in row.colnames:
        dec_val = row['DEC_d']
    else:
        dec_val = row[2]
    ra = Angle(ra_val, unit='degree').degree
    dec = Angle(dec_val, unit='degree').degree
    return float(ra), float(dec)


def _row_types(row) -> str:
    for key in ('alltypes.otypes', 'otypes', 'OTYPE'):
        if key in row.colnames and row[key] is not None:
            return str(row[key])
    return ''


def _row_v_mag(row):
    if 'V' not in row.colnames:
        return None
    val = row['V']
    try:
        if getattr(val, 'mask', False):
            return None
    except Exception:
        pass
    try:
        mag = float(val)
    except (TypeError, ValueError):
        return None
    return mag if np.isfinite(mag) else None


def normalize_simbad_objects(
    result_table,
    *,
    center_ra: float,
    center_dec: float,
    main_names: set[str],
    main_coords: list[tuple[float, float]],
    cluster_id: int = 0,
) -> list[dict[str, Any]]:
    if result_table is None or len(result_table) == 0:
        return []

    center = SkyCoord(center_ra * u.deg, center_dec * u.deg, frame='icrs')
    normalized: list[dict[str, Any]] = []

    for row in result_table:
        name = _row_name(row)
        ra, dec = _row_ra_dec(row)
        if _matches_main_target(name, ra, dec, main_names, main_coords):
            continue

        types_str = _row_types(row)
        object_type = detect_object_type_from_simbad_types(types_str)
        if object_type is None:
            object_type = Object.STAR if '*' in types_str else Object.UNKNOWN

        obj_coord = SkyCoord(ra * u.deg, dec * u.deg, frame='icrs')
        separation_arcmin = float(obj_coord.separation(center).arcminute)

        normalized.append({
            'name': name,
            'ra': ra,
            'dec': dec,
            'object_type': object_type,
            'object_type_display': OBJECT_TYPE_LABELS.get(object_type, 'Unknown'),
            'simbad_types': types_str,
            'v_mag': _row_v_mag(row),
            'separation_arcmin': round(separation_arcmin, 2),
            'cluster_id': cluster_id,
            'field_center_ra': center_ra,
            'field_center_dec': center_dec,
        })

    normalized.sort(key=lambda item: (item['separation_arcmin'], item.get('v_mag') is None, item.get('v_mag') or 99))
    return normalized


def compute_aux_objects(run: ObservationRun) -> dict[str, Any]:
    """
    Query SIMBAD for objects in the FOV of each pointing cluster in the run.
    Returns merged objects list and metadata; does not persist to the run.
    """
    if not run.photometry:
        raise ValueError('Auxiliary SIMBAD lookup is only available for photometry runs')

    clusters = iter_pointing_clusters(run)
    if not clusters:
        raise ValueError('No LIGHT FITS file with coordinates found for this run')

    main_names, main_coords = _main_target_names_and_coords(run)
    all_objects: list[dict[str, Any]] = []
    fields_meta: list[dict[str, Any]] = []

    for cluster_id, cluster_files in enumerate(clusters):
        pks = [df.pk for df in cluster_files]
        rep = _pick_representative_from_queryset(
            DataFile.objects.filter(pk__in=pks)
        )
        if rep is None:
            continue

        center_ra, center_dec, fov_x, fov_y, radius_deg = get_lookup_center_and_fov(rep)
        simbad_radius_str = _radius_str_from_arcmin(radius_deg * 60.0)
        wait_for_aux_simbad_query_slot()
        result_table = _query_region_safe(
            center_ra,
            center_dec,
            simbad_radius_str,
            row_limit=_row_limit(),
        )
        simbad_raw_count = len(result_table) if result_table is not None else 0
        result_table = filter_table_to_footprint(result_table, rep)
        fov_filtered_count = len(result_table) if result_table is not None else 0

        cluster_objects = normalize_simbad_objects(
            result_table,
            center_ra=center_ra,
            center_dec=center_dec,
            main_names=main_names,
            main_coords=main_coords,
            cluster_id=cluster_id,
        )
        for obj in cluster_objects:
            obj['cluster_ids'] = [cluster_id]
        all_objects.extend(cluster_objects)

        fields_meta.append({
            'cluster_id': cluster_id,
            'source_datafile_id': rep.pk,
            'source_file_name': Path(rep.datafile).name if rep.datafile else '',
            'center_ra': center_ra,
            'center_dec': center_dec,
            'fov_x': fov_x,
            'fov_y': fov_y,
            'search_radius_deg': radius_deg,
            'simbad_radius': simbad_radius_str,
            'simbad_match_count': simbad_raw_count,
            'fov_filtered_count': fov_filtered_count,
            'wcs_footprint_applied': build_wcs_from_datafile(rep) is not None,
            'light_file_count': len(cluster_files),
        })

    objects = _dedupe_aux_objects(all_objects)

    meta: dict[str, Any] = {
        'cluster_count': len(fields_meta),
        'fields': fields_meta,
        'simbad_query_count': len(fields_meta),
        'object_count': len(objects),
    }
    # Legacy single-field keys for clients that expect one representative file.
    if len(fields_meta) == 1:
        meta.update(fields_meta[0])

    return {'objects': objects, 'meta': meta}


def build_aux_objects_payload(run: ObservationRun) -> dict[str, Any]:
    status = run.aux_objects_status or None
    return {
        'status': status,
        'objects': run.aux_objects or [],
        'meta': run.aux_objects_meta or {},
        'computed_at': run.aux_objects_computed_at.isoformat() if run.aux_objects_computed_at else None,
        'started_at': run.aux_objects_started_at.isoformat() if run.aux_objects_started_at else None,
        'error': run.aux_objects_error or None,
    }


def pending_is_stale(run: ObservationRun) -> bool:
    if run.aux_objects_status != ObservationRun.AUX_STATUS_PENDING:
        return False
    started = run.aux_objects_started_at
    if not started:
        return True
    age = (timezone.now() - started).total_seconds()
    return age > _pending_stale_seconds()


def save_aux_objects_result(
    run: ObservationRun,
    *,
    objects: list[dict[str, Any]],
    meta: dict[str, Any],
    status: str,
    error: str = '',
) -> None:
    run.aux_objects = objects
    run.aux_objects_meta = meta
    run.aux_objects_status = status
    run.aux_objects_error = error
    now = timezone.now()
    if status == ObservationRun.AUX_STATUS_READY:
        run.aux_objects_computed_at = now
    run.save(
        update_fields=[
            'aux_objects',
            'aux_objects_meta',
            'aux_objects_status',
            'aux_objects_error',
            'aux_objects_computed_at',
        ]
    )
