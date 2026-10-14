"""
Manual classification of data files (exposure type and spectrograph), shared by the single-file and the
bulk admin endpoints.
"""
import logging

from obs_run.models import DataFile
from obs_run.spectrograph import automatic_spectrograph
from ostdata.history_reason import REASON_ADMIN_EXPOSURE_TYPE_USER, REASON_ADMIN_SPECTROGRAPH, save_with_reason
from utilities import (
    evaluate_data_file,
    update_object_photometry_spectroscopy,
    update_observation_run_photometry_spectroscopy,
)

logger = logging.getLogger(__name__)

#   Marker for "leave this field as it is"
UNCHANGED = object()

EXPOSURE_TYPES = {code for code, _ in DataFile.EXPOSURE_TYPE_POSSIBILITIES}
SPECTROGRAPHS = {code for code, _ in DataFile.spectrograph_possibilities}


class ClassificationError(ValueError):
    pass


def validate(exposure_type_user=UNCHANGED, spectrograph=UNCHANGED):
    """Raise ClassificationError for invalid codes (None clears the exposure type / sets spectrograph 'N')."""
    if exposure_type_user not in (UNCHANGED, None, '') and exposure_type_user not in EXPOSURE_TYPES:
        raise ClassificationError(f'Invalid exposure_type_user. Must be one of: {sorted(EXPOSURE_TYPES)}')
    if spectrograph not in (UNCHANGED, None, '') and spectrograph not in SPECTROGRAPHS:
        raise ClassificationError(f'Invalid spectrograph. Must be one of: {sorted(SPECTROGRAPHS)}')


def _update(datafile, exposure_type_user, exposure_type_user_override, spectrograph, spectrograph_override):
    """Apply the values to one file and save it; returns (saved, exposure type changed, spectrograph changed)."""
    fields = []
    exposure_changed = False
    if exposure_type_user is not UNCHANGED:
        datafile.exposure_type_user = exposure_type_user or None
        fields.append('exposure_type_user')
        exposure_changed = True
    if exposure_type_user_override is not None:
        datafile.exposure_type_user_override = exposure_type_user_override
        fields.append('exposure_type_user_override')

    spectrograph_before = datafile.spectrograph
    if spectrograph is not UNCHANGED:
        datafile.spectrograph = spectrograph or 'N'
        fields.append('spectrograph')
    if spectrograph_override is not None:
        datafile.spectrograph_override = spectrograph_override
        fields.append('spectrograph_override')
    if exposure_changed and spectrograph is UNCHANGED:
        # Bias/dark frames carry no spectrograph (manually set spectrographs are kept)
        datafile.spectrograph = automatic_spectrograph(datafile)
        fields.append('spectrograph')

    if not fields:
        return False, False, False
    reason = REASON_ADMIN_EXPOSURE_TYPE_USER if exposure_changed else REASON_ADMIN_SPECTROGRAPH
    save_with_reason(datafile, reason, update_fields=list(dict.fromkeys(fields)))
    return True, exposure_changed, datafile.spectrograph != spectrograph_before


def update_classification(datafiles, exposure_type_user=UNCHANGED, exposure_type_user_override=None,
                          spectrograph=UNCHANGED, spectrograph_override=None):
    """
    Set manual exposure type and/or spectrograph for ``datafiles`` (``UNCHANGED``/None leaves a field as
    it is). Files set to Light get their object association re-evaluated; photometry/spectroscopy flags
    of the affected runs and objects are updated once per run/object. Returns the number of updated files.
    """
    validate(exposure_type_user, spectrograph)
    runs = {}
    objects = {}
    updated = 0
    for datafile in datafiles:
        saved, exposure_changed, spectrograph_changed = _update(
            datafile, exposure_type_user, exposure_type_user_override, spectrograph, spectrograph_override,
        )
        if not saved:
            continue
        updated += 1
        if exposure_changed and datafile.exposure_type_user == 'LI' and datafile.observation_run:
            # Re-evaluate object association so coordinate-based resolution can run for files that were
            # previously misclassified
            try:
                evaluate_data_file(datafile, datafile.observation_run, skip_if_object_has_overrides=True)
            except Exception as e:
                logger.warning(f'Re-evaluation after exposure_type_user=LI failed for datafile {datafile.pk}: {e}')
        if exposure_changed or spectrograph_changed:
            if datafile.observation_run_id:
                runs[datafile.observation_run_id] = datafile.observation_run
            for obj in datafile.object_set.all():
                objects[obj.pk] = obj

    for run in runs.values():
        update_observation_run_photometry_spectroscopy(run)
    for obj in objects.values():
        update_object_photometry_spectroscopy(obj)
    return updated
