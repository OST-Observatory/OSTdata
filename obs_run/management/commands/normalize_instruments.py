from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from obs_run.analyze_fits_header import canonical_instrument
from obs_run.models import DataFile


class Command(BaseCommand):
    help = (
        'Fill DataFile.instrument_normalized (canonical camera name) for existing files. New and saved files '
        'are kept in sync automatically. The raw instrument value is not changed.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would change')
        parser.add_argument('--chunk-size', type=int, default=5000, help='Files per update batch (default: 5000)')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        chunk_size = options['chunk_size']
        changes = Counter()
        pending = defaultdict(list)
        changed = 0

        rows = DataFile.objects.values_list(
            'pk', 'instrument', 'naxis1', 'naxis2', 'pixel_size', 'binning_x', 'binning_y', 'color_sensor',
            'instrument_normalized',
        )
        for pk, instrument, naxis1, naxis2, pixel_size, binning_x, binning_y, color_sensor, current in rows.iterator(
            chunk_size=chunk_size,
        ):
            normalized = canonical_instrument(instrument, naxis1, naxis2, pixel_size, binning_x, binning_y, color_sensor)
            if normalized == current:
                continue
            changes[(instrument or '', normalized)] += 1
            changed += 1
            pending[normalized].append(pk)
            if not dry_run and sum(len(v) for v in pending.values()) >= chunk_size:
                self._flush(pending)
        if not dry_run:
            self._flush(pending)

        self.stdout.write('  files  raw instrument -> normalized')
        for (raw, normalized), count in sorted(changes.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {count:>7}  {raw!r} -> {normalized!r}')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {changed} files would change'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{changed} files updated'))

    @staticmethod
    def _flush(pending):
        # Derived field: plain update without history entries
        for normalized, pks in pending.items():
            DataFile.objects.filter(pk__in=pks).update(instrument_normalized=normalized)
        pending.clear()
