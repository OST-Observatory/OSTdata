"""
Shared DataFile queryset filters for list/download endpoints and Celery ZIP tasks.
"""
from django.db.models import F, FloatField, ExpressionWrapper, Q

from utilities import annotate_effective_exposure_type


def _param_get(params, key, default=None):
    if params is None:
        return default
    if hasattr(params, 'get'):
        return params.get(key, default)
    return default


def _param_getlist(params, key):
    if params is None:
        return []
    if hasattr(params, 'getlist'):
        return params.getlist(key) or []
    val = _param_get(params, key)
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    return [val]


def _parse_bool(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).lower()
    if s in ('true', '1', 'yes'):
        return True
    if s in ('false', '0', 'no'):
        return False
    return None


def apply_datafile_filters(qs, params):
    """
    Apply optional DataFile filters from query params or download-job filter dict.
    """
    if not params:
        return qs

    file_type = _param_get(params, 'file_type')
    if file_type:
        qs = qs.filter(file_type__icontains=file_type)

    main_target = _param_get(params, 'main_target')
    if main_target:
        qs = qs.filter(
            Q(main_target__icontains=main_target) | Q(header_target_name__icontains=main_target)
        )

    exposure_types = _param_getlist(params, 'exposure_type')
    if exposure_types:
        qs = annotate_effective_exposure_type(qs)
        qs = qs.filter(annotated_effective_exposure_type__in=exposure_types)

    spectroscopy = _param_get(params, 'spectroscopy')
    parsed_spec = _parse_bool(spectroscopy)
    if parsed_spec is True:
        qs = qs.filter(spectroscopy=True)
    elif parsed_spec is False:
        qs = qs.filter(spectroscopy=False)

    exptime_min = _param_get(params, 'exptime_min')
    if exptime_min is not None:
        qs = qs.filter(exptime__gte=exptime_min)
    exptime_max = _param_get(params, 'exptime_max')
    if exptime_max is not None:
        qs = qs.filter(exptime__lte=exptime_max)

    file_name = _param_get(params, 'file_name')
    if file_name:
        qs = qs.filter(datafile__icontains=file_name)

    instrument = _param_get(params, 'instrument')
    if instrument:
        qs = qs.filter(instrument__icontains=instrument)

    obs_date_contains = _param_get(params, 'obs_date_contains')
    if obs_date_contains:
        qs = qs.filter(obs_date__icontains=obs_date_contains)

    plate_solved = _param_get(params, 'plate_solved')
    parsed_plate = _parse_bool(plate_solved)
    if parsed_plate is True:
        qs = qs.filter(plate_solved=True)
    elif parsed_plate is False:
        qs = qs.filter(plate_solved=False)

    pixel_min = _param_get(params, 'pixel_count_min')
    pixel_max = _param_get(params, 'pixel_count_max')
    if pixel_min is not None or pixel_max is not None:
        qs = qs.annotate(
            pixel_count=ExpressionWrapper(F('naxis1') * F('naxis2'), output_field=FloatField())
        )
        if pixel_min is not None:
            qs = qs.filter(pixel_count__gte=pixel_min)
        if pixel_max is not None:
            qs = qs.filter(pixel_count__lte=pixel_max)

    return qs
