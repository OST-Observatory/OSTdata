"""
Automatic spectrograph assignment.

The spectrograph is suggested by the ML classifier. Before it is stored, it is constrained by facts the
classifier does not know (derived from the manual corrections in production, see TODO.md):

- bias and dark frames never carry a spectrograph (also darks of spectrograph cameras),
- instruments listed in ``SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS`` (regular expressions, matched
  case-insensitively against ``DataFile.instrument``) were never used as main camera at a spectrograph.

Manually set values (``spectrograph_override``) are never changed.
"""
import re

from django.conf import settings

NONE = 'N'
NO_SPECTROGRAPH_EXPOSURE_TYPES = ('BI', 'DA')

REASON_EXPOSURE_TYPE = 'exposure_type'
REASON_INSTRUMENT = 'instrument'


def imaging_only_instrument(instrument):
    patterns = getattr(settings, 'SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS', [])
    return any(re.search(pattern, instrument or '', re.IGNORECASE) for pattern in patterns)


def constrained_spectrograph(exposure_type, instrument, spectrograph):
    """Apply the constraints to an automatic value -> (spectrograph, reason or None if unchanged)."""
    spectrograph = spectrograph or NONE
    if spectrograph == NONE:
        return NONE, None
    if exposure_type in NO_SPECTROGRAPH_EXPOSURE_TYPES:
        return NONE, REASON_EXPOSURE_TYPE
    if imaging_only_instrument(instrument):
        return NONE, REASON_INSTRUMENT
    return spectrograph, None


def automatic_spectrograph(datafile, spectrograph_ml=None):
    """
    Spectrograph value to store automatically for ``datafile``: the classifier suggestion (or the current
    value if there is none) after applying the constraints; the current value if it was set manually.
    """
    if datafile.spectrograph_override:
        return datafile.spectrograph
    value, _ = constrained_spectrograph(
        datafile.effective_exposure_type, datafile.instrument, spectrograph_ml or datafile.spectrograph,
    )
    return value
