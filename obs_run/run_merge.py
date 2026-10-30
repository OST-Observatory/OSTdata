"""
Merge observation runs with the same name (one run directory ingested twice, e.g. by two concurrent
watchdog processes; the files ended up split between the runs). The oldest run is kept; data files,
download jobs, object links, user permissions and tags of the others are moved to it.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count

from obs_run.models import DataFile, DownloadJob, ObservationRun
from obs_run.utils import should_allow_auto_update

logger = logging.getLogger(__name__)

# Settings of a run compared between duplicates (differences are reported, the kept run's value wins)
_COMPARED_FIELDS = ('is_public', 'photometry', 'spectroscopy', 'reduction_status', 'note')


def duplicate_run_groups():
    """{name: [runs, oldest first]} for every run name used more than once."""
    names = (
        ObservationRun.objects.values('name').annotate(count=Count('pk')).filter(count__gt=1)
        .values_list('name', flat=True)
    )
    return {name: list(ObservationRun.objects.filter(name=name).order_by('pk')) for name in names}


def _recompute_mid_observation_jd(run):
    if not should_allow_auto_update(run, 'mid_observation_jd'):
        return
    files = DataFile.objects.filter(observation_run=run, hjd__gt=2451545)
    first = files.order_by('hjd').values_list('hjd', flat=True).first()
    last = files.order_by('-hjd').values_list('hjd', flat=True).first()
    run.mid_observation_jd = 0.0 if first is None else float(first + (last - first) / 2.0)
    run.save(update_fields=['mid_observation_jd'])


def merge_runs(keeper, duplicates, dry_run=False):
    """Move everything of `duplicates` to `keeper` and delete them; returns a report."""
    report = {
        'name': keeper.name, 'keep': keeper.pk, 'merge': [run.pk for run in duplicates],
        'datafiles': 0, 'download_jobs': 0, 'objects': 0, 'differences': [],
    }
    for run in duplicates:
        report['datafiles'] += run.datafile_set.count()
        report['download_jobs'] += run.download_jobs.count()
        report['objects'] += run.object_set.count()
        for field in _COMPARED_FIELDS:
            kept, other = getattr(keeper, field), getattr(run, field)
            if kept != other and other not in ('', None) and not (field == 'reduction_status' and other == 'NE'):
                report['differences'].append(f'{field}: #{keeper.pk}={kept!r}, #{run.pk}={other!r}')
    if dry_run:
        return report

    with transaction.atomic():
        update_fields = []
        for run in duplicates:
            # Plain updates: moving files between duplicates is no change worth a history entry each
            DataFile.objects.filter(observation_run=run).update(observation_run=keeper)
            DownloadJob.objects.filter(run=run).update(run=keeper)
            for obj in run.object_set.all():
                obj.observation_run.add(keeper)
            keeper.readonly_users.add(*run.readonly_users.all())
            keeper.readwrite_users.add(*run.readwrite_users.all())
            keeper.managers.add(*run.managers.all())
            keeper.tags.add(*run.tags.all())
            # Manual entries made on a duplicate are not lost
            if not (keeper.note or '').strip() and (run.note or '').strip():
                keeper.note = run.note
                update_fields.append('note')
            if keeper.reduction_status == 'NE' and run.reduction_status not in ('NE', '', None):
                keeper.reduction_status = run.reduction_status
                update_fields.append('reduction_status')
            run.delete()
        if update_fields:
            keeper.save(update_fields=sorted(set(update_fields)))

    # Derived run data now covers all files
    from utilities import update_observation_run_photometry_spectroscopy

    _recompute_mid_observation_jd(keeper)
    update_observation_run_photometry_spectroscopy(keeper)
    try:
        from obs_run.tasks import enqueue_aux_objects_for_run
        enqueue_aux_objects_for_run(keeper.pk, force=True)
    except Exception:
        logger.warning('Could not enqueue aux objects for merged run %s', keeper.pk, exc_info=True)
    logger.info('Merged duplicate runs %s into #%s (%s)', report['merge'], keeper.pk, keeper.name)
    return report


def merge_duplicate_runs(dry_run=True):
    """Merge every group of runs with the same name; list of reports."""
    return [merge_runs(runs[0], runs[1:], dry_run=dry_run) for runs in duplicate_run_groups().values()]
