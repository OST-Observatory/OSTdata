"""
Comparison of a (new) classifier with the stored classification, used by
``classify_exposure_types --compare``. Nothing is saved.

Per file the stored values (old) are compared with the values the classifier would store now (new):
ML exposure type, effective exposure type (obs_run/exposure_type.py) and spectrograph after the rules
(obs_run/spectrograph.py). Manual labels (``exposure_type_user``, ``spectrograph_override``) are the
reference for the accuracy of old and new suggestions.
"""
import copy
from collections import Counter, defaultdict

from obs_run.exposure_type import UNKNOWN, effective_exposure_type
from obs_run.spectrograph import automatic_spectrograph

NOT_RUN = '-'  # ML never ran on the file


def _automatic(datafile, spectrograph_ml):
    """Spectrograph the rules would store, ignoring a manually set value."""
    clone = copy.copy(datafile)
    clone.spectrograph_override = False
    return automatic_spectrograph(clone, spectrograph_ml)


def compare_row(datafile, result):
    """Old and new values of one file; ``result``: ExposureTypeClassifier.classify_datafile()."""
    from obs_run.ml_classification import apply_ml_result

    new = copy.copy(datafile)
    new.spectrograph_override = False  # automatic value, also for files with a manual spectrograph
    apply_ml_result(new, result)
    manual_spectrograph = bool(datafile.spectrograph_override)
    # like classify_exposure_types: a file counts as classified once the confidence is set (the field defaults to UK)
    old_ml = (datafile.exposure_type_ml or UNKNOWN) if datafile.exposure_type_ml_confidence is not None else NOT_RUN
    return {
        'id': datafile.pk,
        'path': str(datafile.datafile),
        'run': datafile.observation_run.name if datafile.observation_run_id else None,
        'header': datafile.exposure_type or UNKNOWN,
        'user': datafile.exposure_type_user or '',
        'old_ml': old_ml,
        'new_ml': new.exposure_type_ml or UNKNOWN,
        'new_top_class': new.ml_top_class,
        'new_confidence': new.exposure_type_ml_confidence,
        'old_effective': datafile.effective_exposure_type,
        'new_effective': effective_exposure_type(datafile.exposure_type, new.exposure_type_ml,
                                                 datafile.exposure_type_user, name_rule=datafile.exposure_type_rule),
        'manual_spectrograph': manual_spectrograph,
        # stored value; for manually set spectrographs the old automatic value if it can be re-derived
        'old_spectrograph': (_automatic(datafile, datafile.spectrograph_ml) if datafile.spectrograph_ml else None)
        if manual_spectrograph else (datafile.spectrograph or 'N'),
        'new_spectrograph': new.spectrograph or 'N',
        'spectrograph': datafile.spectrograph or 'N',
    }


def _changes(rows, old_key, new_key, examples):
    counts, paths = Counter(), defaultdict(list)
    for row in rows:
        if row[old_key] != row[new_key]:
            key = f'{row[old_key]} -> {row[new_key]}'
            counts[key] += 1
            if len(paths[key]) < examples:
                paths[key].append(row['path'])
    return [{'change': key, 'n': n, 'examples': paths[key]} for key, n in counts.most_common()]


def _suggestion_quality(rows, key):
    """Share of correct / abstained (or not run) / wrong suggestions against the manual label."""
    n = len(rows)
    correct = sum(row[key] == row['user'] for row in rows)
    no_class = sum(row[key] in (UNKNOWN, NOT_RUN) for row in rows)
    return {
        'n': n,
        'correct': round(correct / n, 4) if n else None,
        'abstained_or_not_run': round(no_class / n, 4) if n else None,
        'wrong': round((n - correct - no_class) / n, 4) if n else None,
    }


def summarize(rows, examples=3):
    unlabelled = [row for row in rows if not row['user']]
    labelled = [row for row in rows if row['user'] and row['user'] != UNKNOWN]
    manual_spec = [row for row in rows if row['manual_spectrograph']]
    manual_spec_old = [row for row in manual_spec if row['old_spectrograph'] is not None]
    wrong_new = [row for row in labelled if row['new_ml'] not in (UNKNOWN, NOT_RUN, row['user'])]

    def share(subset, key):
        return round(sum(row[key] == row['spectrograph'] for row in subset) / len(subset), 4) if subset else None

    return {
        'files': len(rows),
        'ml_changes': _changes(rows, 'old_ml', 'new_ml', examples),
        'without_manual_label': {
            'n': len(unlabelled),
            'uk_before': sum(row['old_effective'] == UNKNOWN for row in unlabelled),
            'uk_after': sum(row['new_effective'] == UNKNOWN for row in unlabelled),
            'changes': _changes(unlabelled, 'old_effective', 'new_effective', examples),
        },
        'with_manual_label': {
            'old': _suggestion_quality(labelled, 'old_ml'),
            'new': _suggestion_quality(labelled, 'new_ml'),
            'new_errors': _changes(wrong_new, 'user', 'new_ml', examples),  # manual label -> new suggestion
        },
        'spectrograph': {
            'changes_without_manual_value': _changes([row for row in rows if not row['manual_spectrograph']],
                                                     'old_spectrograph', 'new_spectrograph', examples),
            'manual': {
                'n': len(manual_spec),
                'new_correct': share(manual_spec, 'new_spectrograph'),
                'old_n': len(manual_spec_old),
                'old_correct': share(manual_spec_old, 'old_spectrograph'),
            },
        },
    }
