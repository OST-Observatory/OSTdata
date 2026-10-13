from collections import Counter

from django.core.management.base import BaseCommand

from obs_run.models import DataFile
from obs_run.spectrograph import NONE, constrained_spectrograph
from ostdata.history_reason import REASON_TASK_SPECTROGRAPH_RULES, save_with_reason
from utilities import (
    annotate_effective_exposure_type,
    update_object_photometry_spectroscopy,
    update_observation_run_photometry_spectroscopy,
)


class Command(BaseCommand):
    help = (
        'Apply the spectrograph constraints (obs_run/spectrograph.py) to existing files: no spectrograph for '
        'bias/dark frames and imaging-only instruments. Manually set spectrographs are not touched.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only list what would change',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='Print every affected file (id, run, path, change, reason)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        queryset = annotate_effective_exposure_type(
            DataFile.objects.filter(spectrograph_override=False).exclude(spectrograph=NONE)
        ).select_related('observation_run')

        changes = Counter()
        runs = set()
        objects = set()
        for datafile in queryset.iterator(chunk_size=1000):
            value, reason = constrained_spectrograph(
                datafile.annotated_effective_exposure_type, datafile.instrument, datafile.spectrograph,
            )
            if value == datafile.spectrograph:
                continue
            change = f'{datafile.spectrograph} -> {value} ({reason})'
            changes[change] += 1
            if options['list']:
                run_name = datafile.observation_run.name if datafile.observation_run else '-'
                self.stdout.write(f'  {datafile.pk:>8}  {run_name:<30}  {change:<28}  {datafile.datafile}')
            if dry_run:
                continue
            datafile.spectrograph = value
            save_with_reason(datafile, REASON_TASK_SPECTROGRAPH_RULES, update_fields=['spectrograph'])
            if datafile.observation_run_id:
                runs.add(datafile.observation_run)
            objects.update(datafile.object_set.all())

        for run in runs:
            update_observation_run_photometry_spectroscopy(run)
        for obj in objects:
            update_object_photometry_spectroscopy(obj)

        self.stdout.write('')
        for change, count in changes.most_common():
            self.stdout.write(f'  {count:>8}  {change}')
        total = sum(changes.values())
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {total} files would change'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'{total} files changed, {len(runs)} runs and {len(objects)} objects re-evaluated'
            ))
