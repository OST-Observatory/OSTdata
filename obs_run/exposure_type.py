"""
Effective exposure type: single source of truth.

A DataFile has three exposure type sources: the FITS header (``exposure_type``), the ML classifier
(``exposure_type_ml``) and a manual label (``exposure_type_user``). The effective type combines them.
The Python function (used by ``DataFile.effective_exposure_type``) and the SQL expression (used for
querysets and aggregations) must stay equivalent - see ``obs_run/tests/test_exposure_type.py``.

Rules (setting ``EXPOSURE_TYPE_EFFECTIVE_RULE``):

- ``header_first`` (default): user label > header if ML has no class > ML if header is UK >
  header if ML agrees > UK (header and ML disagree, needs review).
- ``agree``: legacy rule. User label > ML if it equals the header > UK if ML is set but differs
  (this includes ML abstaining) > header.

"ML has no class" means ``exposure_type_ml`` is NULL, empty or 'UK' (not run or abstained).
"""
from django.conf import settings
from django.db.models import Case, CharField, F, Q, Value, When
from django.db.models.lookups import Exact

UNKNOWN = 'UK'

RULE_HEADER_FIRST = 'header_first'
RULE_AGREE = 'agree'
RULES = (RULE_HEADER_FIRST, RULE_AGREE)


def get_rule():
    rule = getattr(settings, 'EXPOSURE_TYPE_EFFECTIVE_RULE', RULE_HEADER_FIRST)
    if rule not in RULES:
        raise ValueError(f'EXPOSURE_TYPE_EFFECTIVE_RULE must be one of {RULES}, got {rule!r}')
    return rule


def _clean(value):
    return value or ''


def effective_exposure_type(header, ml, user, rule=None):
    """Return the effective exposure type code for raw field values."""
    rule = rule or get_rule()
    user = _clean(user)
    if user:
        return user
    header = _clean(header)
    ml = _clean(ml)

    if rule == RULE_AGREE:
        if ml:
            return ml if ml == header else UNKNOWN
        return header

    if not ml or ml == UNKNOWN:
        return header
    if header in ('', UNKNOWN):
        return ml
    return header if ml == header else UNKNOWN


def effective_exposure_type_expression(field_prefix='', rule=None):
    """SQL expression equivalent to ``effective_exposure_type`` (``field_prefix`` e.g. 'datafile__')."""
    rule = rule or get_rule()
    user = f'{field_prefix}exposure_type_user'
    ml = f'{field_prefix}exposure_type_ml'
    header = f'{field_prefix}exposure_type'

    user_set = Q(**{f'{user}__isnull': False}) & ~Q(**{user: ''})
    ml_set = Q(**{f'{ml}__isnull': False}) & ~Q(**{ml: ''})

    if rule == RULE_AGREE:
        whens = [
            When(user_set, then=F(user)),
            When(ml_set & Q(**{ml: F(header)}), then=F(ml)),
            When(ml_set, then=Value(UNKNOWN)),
        ]
        default = F(header)
    else:
        whens = [
            When(user_set, then=F(user)),
            When(~ml_set | Q(**{ml: UNKNOWN}), then=F(header)),
            When(Q(**{header: UNKNOWN}) | Q(**{header: ''}), then=F(ml)),
            When(Q(**{ml: F(header)}), then=F(header)),
        ]
        default = Value(UNKNOWN)
    return Case(*whens, default=default, output_field=CharField(max_length=2))


def effective_exposure_type_q(exposure_type_code, field_prefix='', rule=None):
    """Q object matching files whose effective type is ``exposure_type_code`` (usable in Count filters)."""
    return Q(Exact(effective_exposure_type_expression(field_prefix, rule), Value(exposure_type_code)))


# Classifier classes (ost_image_classification) by (exposure type, spectrograph)
CLASSIFIER_CLASSES = {
    ('BI', 'N'): 'bias',
    ('DA', 'N'): 'darks',
    ('FL', 'N'): 'flats',
    ('FL', 'D'): 'flat_dados',
    ('FL', 'B'): 'flat_baches',
    ('LI', 'N'): 'deep_sky',
    ('LI', 'D'): 'spectrum_dados',
    ('LI', 'B'): 'spectrum_baches',
    ('LI', 'E'): 'einsteinturm',
    ('WA', 'D'): 'wavelength_calibration_dados',
    ('WA', 'B'): 'wavelength_calibration_baches',
}


def classifier_class_name(exposure_type, spectrograph):
    """Classifier class for an exposure type/spectrograph pair, None if the combination is not valid."""
    return CLASSIFIER_CLASSES.get((exposure_type, spectrograph or 'N'))


def format_default_exposure_type(file_type):
    """
    Exposure type for formats without exposure type metadata: 'LI' for the formats in
    ``EXPOSURE_TYPE_LIGHT_DEFAULT_FORMATS`` (manually labelled as light in ~97 % of cases), else UK.
    """
    formats = getattr(settings, 'EXPOSURE_TYPE_LIGHT_DEFAULT_FORMATS', [])
    return 'LI' if (file_type or '').upper() in {f.upper() for f in formats} else UNKNOWN
