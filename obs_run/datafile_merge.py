"""
Merge data file entries with the same path (one file ingested twice, e.g. by two concurrent watchdog
processes; merging the duplicate runs then put both entries into the same run). One entry is kept:
plate solved, with manual values (user classification, overrides) or the AI notice first, then the
oldest. Object links, plate solving failures and manual values of the others move to it.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count

from obs_run.models import DataFile, PlateSolveFailure

logger = logging.getLogger(__name__)

# Override flag -> fields it protects: copied from a duplicate when only the duplicate has the override
_OVERRIDES = {
    'exposure_type_override': ('exposure_type',),
    'exposure_type_user_override': ('exposure_type_user',),
    'spectrograph_override': ('spectrograph',),
    'instrument_override': ('instrument',),
    'telescope_override': ('telescope',),
    'main_target_override': ('main_target',),
    'quality_flag_override': ('quality_flag',),
    'spectroscopy_override': ('spectroscopy',),
}


def duplicate_datafile_groups():
    """{path: [entries, kept entry first]} for every path tracked more than once."""
    paths = (
        DataFile.objects.values('datafile').annotate(count=Count('pk')).filter(count__gt=1)
        .values_list('datafile', flat=True)
    )
    return {path: sorted(DataFile.objects.filter(datafile=path), key=_keep_priority) for path in paths}


def _manual_values(datafile):
    return sum(bool(getattr(datafile, flag)) for flag in _OVERRIDES) + bool(datafile.exposure_type_user)


def _keep_priority(datafile):
    return (
        not datafile.plate_solved,
        -_manual_values(datafile),
        datafile.ai_notice_added_at is None,
        datafile.pk,
    )


def _copies(keeper, duplicate):
    """Manual values only the duplicate has: {name: fields to copy (incl. the override flag)}."""
    copies = {}
    for flag, fields in _OVERRIDES.items():
        if getattr(duplicate, flag) and not getattr(keeper, flag):
            copies[flag] = (flag, *fields)
    if duplicate.exposure_type_user and not keeper.exposure_type_user and 'exposure_type_user_override' not in copies:
        copies['exposure_type_user'] = ('exposure_type_user',)
    return copies


def merge_datafiles(keeper, duplicates, dry_run=False):
    """Move links and manual values of `duplicates` to `keeper` and delete them; returns a report."""
    report = {'path': keeper.datafile, 'keep': keeper.pk, 'merge': [d.pk for d in duplicates],
              'objects': 0, 'copied': []}
    keeper_objects = set(keeper.object_set.values_list('pk', flat=True))
    for duplicate in duplicates:
        report['objects'] += duplicate.object_set.exclude(pk__in=keeper_objects).count()
        report['copied'] += [f'{name} from #{duplicate.pk}' for name in _copies(keeper, duplicate)]
    if dry_run:
        return report

    with transaction.atomic():
        update_fields = set()
        for duplicate in duplicates:
            for obj in duplicate.object_set.all():
                obj.datafiles.add(keeper)
            known_tools = set(keeper.plate_solve_failures.values_list('tool', flat=True))
            PlateSolveFailure.objects.filter(datafile=duplicate).exclude(tool__in=known_tools) \
                .update(datafile=keeper)
            for fields in _copies(keeper, duplicate).values():
                for field in fields:
                    setattr(keeper, field, getattr(duplicate, field))
                update_fields.update(fields)
            duplicate.delete()
        if update_fields:
            keeper.save(update_fields=sorted(update_fields))
    logger.info('Merged duplicate data files %s into #%s (%s)', report['merge'], keeper.pk, keeper.datafile)
    return report


def merge_duplicate_datafiles(dry_run=True):
    """Merge every group of data file entries with the same path; list of reports."""
    return [merge_datafiles(entries[0], entries[1:], dry_run=dry_run)
            for entries in duplicate_datafile_groups().values()]
