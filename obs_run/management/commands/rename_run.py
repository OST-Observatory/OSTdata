import os

from django.core.management.base import BaseCommand, CommandError

from obs_run.models import ObservationRun, DataFile


class Command(BaseCommand):
    help = "Rename an ObservationRun and rewrite all DataFile paths accordingly."

    def add_arguments(self, parser):
        parser.add_argument('old_name', type=str, help='Current run folder name (relative to data root)')
        parser.add_argument('new_name', type=str, help='New run folder name (relative to data root)')
        parser.add_argument('--data-root', type=str, default=None, help='Absolute data root. If omitted, will infer from common prefix of existing files')

    def handle(self, *args, **options):
        old_name = options['old_name'].strip().strip('/')
        new_name = options['new_name'].strip().strip('/')
        data_root_opt = options.get('data_root')

        try:
            run = ObservationRun.objects.get(name=old_name)
        except ObservationRun.DoesNotExist:
            raise CommandError(f"ObservationRun with name '{old_name}' not found")

        # Find all files belonging to this run
        files_qs = DataFile.objects.filter(observation_run=run)
        if not files_qs.exists():
            self.stdout.write(self.style.WARNING('No files found for this run. Proceeding with run rename only.'))

        # Determine data root
        if data_root_opt:
            data_root = data_root_opt
        else:
            # Infer as the longest common prefix across file paths up to old_name
            # Fallback to prefix of first file
            first = files_qs.first()
            if first is None:
                raise CommandError('Cannot infer data root without files. Provide --data-root.')
            path = str(first.datafile)
            # Find segment ending with old_name
            try:
                idx = path.rindex(old_name)
                data_root = path[:idx]
            except ValueError:
                # As a fallback, use dirname of the path up to old_name-like split
                parts = path.split(os.sep)
                if old_name in parts:
                    k = parts.index(old_name)
                    data_root = os.sep.join(parts[:k]) + os.sep
                else:
                    raise CommandError('Failed to infer data root; specify --data-root')

        if not data_root.endswith(os.sep):
            data_root = data_root + os.sep

        old_prefix = os.path.join(data_root, old_name) + os.sep
        new_prefix = os.path.join(data_root, new_name) + os.sep

        # Update run name
        run.name = new_name
        run.save(update_fields=['name'])

        # Rewrite file paths
        updated = 0
        for df in files_qs:
            try:
                p = str(df.datafile)
                if p.startswith(old_prefix):
                    df.datafile = p.replace(old_prefix, new_prefix, 1)
                    df.save(update_fields=['datafile'])
                    updated += 1
            except Exception as e:
                self.stderr.write(f"Failed updating DataFile #{df.pk}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Renamed run '{old_name}' -> '{new_name}', updated {updated} file paths."))


