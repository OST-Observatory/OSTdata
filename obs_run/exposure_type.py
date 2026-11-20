"""
Effective exposure type: single source of truth.

A DataFile has four exposure type sources: the FITS header (``exposure_type``), the name rule
(``exposure_type_rule``: arc lamp names in file name or OBJECT, see ``name_rule_exposure_type``), the ML
classifier (``exposure_type_ml``) and a manual label (``exposure_type_user``). The effective type combines them.
The Python function (used by ``DataFile.effective_exposure_type``) and the SQL expression (used for
querysets and aggregations) must stay equivalent - see ``obs_run/tests/test_exposure_type.py``.

Rules (setting ``EXPOSURE_TYPE_EFFECTIVE_RULE``), both after user label > name rule:

- ``header_first`` (default): header if ML has no class > ML if header is UK >
  header if ML agrees > UK (header and ML disagree, needs review).
- ``agree``: legacy rule. ML if it equals the header > UK if ML is set but differs
  (this includes ML abstaining) > header.

"ML has no class" means ``exposure_type_ml`` is NULL, empty or 'UK' (not run or abstained).
"""
import re
from pathlib import PurePath

from django.conf import settings
from django.db.models import Case, CharField, F, Q, Value, When
from django.db.models.lookups import Exact

UNKNOWN = 'UK'

RULE_HEADER_FIRST = 'header_first'
RULE_AGREE = 'agree'
RULES = (RULE_HEADER_FIRST, RULE_AGREE)


# Name rule: arc lamp names in the file name or OBJECT mark wavelength calibration frames whose header says
# light or nothing (e.g. 'DADOS_Ar-Ne-0001_1s.fit' with IMAGETYP 'Light Frame'). Whole tokens only, so
# 'arcturus' or 'near' do not match; 'ne_ar' needs a separator ('near').
WAVE = 'WA'
ARC_LAMP_PATTERN = re.compile(
    r'(?<![a-z])(th[-_ ]?ar|ar[-_ ]?ne|ne[-_ ]ar|hg[-_ ]?ar|neon|argon|wavecal|arc)(?![a-z])', re.IGNORECASE,
)
NAME_RULE_HEADER_TYPES = ('LI', UNKNOWN, '')


def name_rule_exposure_type(header, path, object_name, enabled=None):
    """
    'WA' if the header type is light/unknown and file name or OBJECT names an arc lamp, else ''. Always ''
    unless the rule is enabled (``enabled``, default: setting ``EXPOSURE_TYPE_NAME_RULE``).
    """
    if enabled is None:
        enabled = getattr(settings, 'EXPOSURE_TYPE_NAME_RULE', False)
    if not enabled or (header or '') not in NAME_RULE_HEADER_TYPES:
        return ''
    return WAVE if arc_lamp_token(path, object_name) else ''


def arc_lamp_token(path, object_name):
    """Arc lamp token in the file name or OBJECT, normalised ('Ar-Ne' -> 'arne'), None if there is none."""
    for name in (PurePath(str(path or '')).name, str(object_name or '')):
        match = ARC_LAMP_PATTERN.search(name)
        if match:
            return re.sub(r'[-_ ]', '', match.group(1).lower())
    return None


def get_rule():
    rule = getattr(settings, 'EXPOSURE_TYPE_EFFECTIVE_RULE', RULE_HEADER_FIRST)
    if rule not in RULES:
        raise ValueError(f'EXPOSURE_TYPE_EFFECTIVE_RULE must be one of {RULES}, got {rule!r}')
    return rule


def _clean(value):
    return value or ''


def effective_exposure_type(header, ml, user, rule=None, name_rule=None):
    """Return the effective exposure type code for raw field values (``name_rule``: exposure_type_rule)."""
    rule = rule or get_rule()
    user = _clean(user)
    if user:
        return user
    if _clean(name_rule):
        return name_rule
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
    name_rule = f'{field_prefix}exposure_type_rule'

    user_set = Q(**{f'{user}__isnull': False}) & ~Q(**{user: ''})
    name_rule_set = Q(**{f'{name_rule}__isnull': False}) & ~Q(**{name_rule: ''})
    ml_set = Q(**{f'{ml}__isnull': False}) & ~Q(**{ml: ''})

    if rule == RULE_AGREE:
        whens = [
            When(user_set, then=F(user)),
            When(name_rule_set, then=F(name_rule)),
            When(ml_set & Q(**{ml: F(header)}), then=F(ml)),
            When(ml_set, then=Value(UNKNOWN)),
        ]
        default = F(header)
    else:
        whens = [
            When(user_set, then=F(user)),
            When(name_rule_set, then=F(name_rule)),
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


# Valid (exposure type, spectrograph) pairs: the classifier classes plus spectrographs the classifier does not
# know yet (UVEX: so far only from the SPECTRO keyword of OST_OCS files, not exported as training data)
VALID_COMBINATIONS = frozenset(CLASSIFIER_CLASSES) | {('LI', 'U'), ('FL', 'U'), ('WA', 'U')}


def valid_combination(exposure_type, spectrograph):
    """Whether an exposure type/spectrograph pair is valid (bias and darks carry no spectrograph)."""
    return (exposure_type, spectrograph or 'N') in VALID_COMBINATIONS


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
