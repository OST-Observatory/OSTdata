from collections import Counter

from astropy.io import fits
from django.core.management.base import BaseCommand
from django.db.models import Q

from obs_run.analyze_fits_header import header_filter
from obs_run.models import DataFile
from ostdata.history_reason import REASON_TASK_BACKFILL_FILTERS, save_with_reason

FITS_FILES = (
    Q(file_type__iexact='FITS') | Q(datafile__iendswith='.fits') | Q(datafile__iendswith='.fit')
    | Q(datafile__iendswith='.fts')
)


class Command(BaseCommand):
    help = (
        'Fill DataFile.image_filter from the FILTER keyword of existing FITS files. Only this field is '
        'written (with history reason task:backfill_filters); unlike reanalyze_fits, no other header values, '
        'targets or object associations are touched and no network services are used. By default only '
        'files without a filter are read.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would change')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of files to read')
        parser.add_argument(
            '--all', action='store_true',
            help='Also re-read files that already have a filter (e.g. after a header was corrected)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        queryset = DataFile.objects.filter(FITS_FILES)
        if not options['all']:
            queryset = queryset.filter(image_filter='')
        queryset = queryset.order_by('pk')
        if options['limit']:
            queryset = queryset[:options['limit']]

        values = Counter()
        checked = changed = errors = 0
        for datafile in queryset.iterator(chunk_size=500):
            if checked and checked % 5000 == 0:
                self.stdout.write(f'  {checked} files read, {changed} with a new filter value')
            checked += 1
            try:
                header = fits.getheader(datafile.datafile, 0, ignore_missing_simple=True)
            except Exception as exc:
                errors += 1
                if errors <= 10:
                    self.stdout.write(self.style.ERROR(f'  #{datafile.pk} {datafile.datafile}: {exc}'))
                continue
            value = header_filter(header)
            if value == datafile.image_filter:
                continue
            changed += 1
            values[(datafile.image_filter, value)] += 1
            if not dry_run:
                datafile.image_filter = value
                save_with_reason(datafile, REASON_TASK_BACKFILL_FILTERS, update_fields=['image_filter'])

        self.stdout.write(f'{checked} files read, {changed} with a new filter value, {errors} unreadable')
        self.stdout.write('  files  filter: old -> new')
        for (old, new), count in sorted(values.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {count:>7}  {old!r} -> {new!r}')
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {changed} files would change'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{changed} files updated'))
