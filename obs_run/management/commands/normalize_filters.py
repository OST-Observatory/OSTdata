from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from obs_run.filter_names import normalize_filter
from obs_run.models import DataFile


class Command(BaseCommand):
    help = (
        'Recompute DataFile.filter_normalized (canonical filter name, obs_run/filter_names.py) from the stored '
        'filter, e.g. after the alias table changed. Reads no files; the raw filter value is not changed. New '
        'and saved files are kept in sync automatically.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would change')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        changes = Counter()
        pending = defaultdict(list)
        rows = DataFile.objects.exclude(image_filter='', filter_normalized='').values_list(
            'pk', 'image_filter', 'filter_normalized',
        )
        for pk, raw, current in rows.iterator(chunk_size=5000):
            normalized = normalize_filter(raw)
            if normalized != current:
                changes[(raw, current, normalized)] += 1
                pending[normalized].append(pk)

        if not dry_run:
            # Derived field: plain update without history entries
            for normalized, pks in pending.items():
                for start in range(0, len(pks), 5000):
                    DataFile.objects.filter(pk__in=pks[start:start + 5000]).update(filter_normalized=normalized)

        self.stdout.write('  files  filter (raw): normalized old -> new')
        for (raw, old, new), count in sorted(changes.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {count:>7}  {raw!r}: {old!r} -> {new!r}')
        total = sum(changes.values())
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {total} files would change'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{total} files updated'))
