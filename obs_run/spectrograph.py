"""
Automatic spectrograph assignment.

The spectrograph is suggested by the ML classifier. Before it is stored, it is constrained by facts the
classifier does not know (derived from the manual corrections in production, see TODO.md):

- bias and dark frames never carry a spectrograph (also darks of spectrograph cameras),
- instruments listed in ``SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS`` (regular expressions, matched
  case-insensitively against ``DataFile.instrument``) were never used as main camera at a spectrograph.

Files written by OST_OCS carry the spectrograph in the ``SPECTRO`` keyword (``DataFile.spectrograph_header``).
It replaces the classifier suggestion and the instrument constraint; bias and darks still carry none.

Manually set values (``spectrograph_override``) are never changed.
"""
import re

from django.conf import settings

NONE = 'N'

# SPECTRO keyword values (header specification of OST_OCS) -> DataFile.spectrograph codes
SPECTRO_CODES = {'BACHES': 'B', 'DADOS': 'D', 'UVEX': 'U', 'NONE': NONE}
# SWCREATE prefix of files written by OST_OCS: only their SPECTRO keyword is trusted
OST_OCS_SOFTWARE_PREFIX = 'OST_OCS'
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


def written_by_ost_ocs(header):
    """Whether a FITS header was written by OST_OCS (SWCREATE 'OST_OCS <version>')."""
    software = header.get('SWCREATE', '') if header is not None else ''
    return str(software or '').strip().upper().startswith(OST_OCS_SOFTWARE_PREFIX)


def header_spectrograph(header):
    """
    Spectrograph code from the SPECTRO keyword of an OST_OCS file; None for files of other software (their
    headers are not reliable) and for missing or unknown values.
    """
    if not written_by_ost_ocs(header):
        return None
    value = str(header.get('SPECTRO', '') or '').strip().upper()
    return SPECTRO_CODES.get(value)


def automatic_spectrograph(datafile, spectrograph_ml=None):
    """
    Spectrograph value to store automatically for ``datafile``: the current value if it was set manually;
    else the SPECTRO value of an OST_OCS file (``spectrograph_header``, none for bias/darks); else the
    classifier suggestion (or the current value if there is none) after applying the constraints.
    """
    if datafile.spectrograph_override:
        return datafile.spectrograph
    if datafile.spectrograph_header:
        if datafile.effective_exposure_type in NO_SPECTROGRAPH_EXPOSURE_TYPES:
            return NONE
        return datafile.spectrograph_header
    value, _ = constrained_spectrograph(
        datafile.effective_exposure_type, datafile.instrument, spectrograph_ml or datafile.spectrograph,
    )
    return value
