from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from obs_run.image_quality import NOT_CHECKED, OVEREXPOSED, QUALITY_FLAG_CHOICES, check_datafile
from obs_run.models import DataFile
from utilities import annotate_effective_exposure_type

BUCKETS = (0.0, 0.001, 0.01, 0.05, 0.2, 0.5, 1.01)


def _bucket(value, edges=BUCKETS):
    if value is None:
        return 'n/a'
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= value < hi:
            return f'{lo:g}-{hi:g}'
    return f'>={edges[-1]:g}'


class Command(BaseCommand):
    help = (
        'Check the image quality (over-exposed, empty, unreadable) of existing files and store the flag. '
        'Reads pixel data file by file (memory friendly); resumable, only unchecked files by default.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Compute and report only, do not save')
        parser.add_argument('--recheck', action='store_true', help='Also files that were checked before')
        parser.add_argument('--flag', nargs='+', choices=[code for code, _ in QUALITY_FLAG_CHOICES],
                            help='Only (re)check files that currently have one of these flags, e.g. --flag EM')
        parser.add_argument('--limit', type=int, default=None, help='At most N files')
        parser.add_argument('--run', type=str, default=None, help='Only runs whose name contains this text')
        parser.add_argument('--examples', type=int, default=20, help='Over-exposed example paths to print')

    def handle(self, *args, **options):
        queryset = DataFile.objects.filter(quality_flag_override=False).order_by('pk')
        if options['flag']:
            queryset = queryset.filter(quality_flag__in=options['flag'])
        elif not options['recheck']:
            queryset = queryset.filter(quality_flag=NOT_CHECKED)
        if options['run']:
            queryset = queryset.filter(observation_run__name__icontains=options['run'])
        queryset = annotate_effective_exposure_type(queryset).values_list(
            'pk', 'datafile', 'file_type', 'annotated_effective_exposure_type',
        )
        if options['limit']:
            queryset = queryset[:options['limit']]

        flags = Counter()
        saturated_by_type = defaultdict(Counter)
        median_by_type = defaultdict(Counter)
        examples = []
        processed = 0
        for pk, path, file_type, exposure_type in queryset.iterator(chunk_size=500):
            probe = DataFile(datafile=path, file_type=file_type)
            flag, saturated, median_level = check_datafile(probe)
            flags[flag] += 1
            saturated_by_type[exposure_type][_bucket(saturated)] += 1
            median_by_type[exposure_type][_bucket(median_level, (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 2.0))] += 1
            if flag == OVEREXPOSED and len(examples) < options['examples']:
                examples.append(f'{exposure_type}  sat {saturated}  median {median_level}  {path}')
            if not options['dry_run']:
                # Derived values: plain update without history entries
                DataFile.objects.filter(pk=pk).update(
                    quality_flag=flag, saturated_fraction=saturated, median_level=median_level,
                )
            processed += 1
            if processed % 1000 == 0:
                self.stdout.write(f'  {processed} files ...')

        self.stdout.write('\nFlags:')
        for flag, count in flags.most_common():
            self.stdout.write(f'  {count:>8}  {flag}')
        for title, table in (('Saturated pixel fraction', saturated_by_type), ('Median level / full scale', median_by_type)):
            self.stdout.write(f'\n{title} by effective exposure type:')
            for exposure_type, buckets in sorted(table.items()):
                cells = ', '.join(f'{k}: {v}' for k, v in sorted(buckets.items()))
                self.stdout.write(f'  {exposure_type}: {cells}')
        if examples:
            self.stdout.write('\nOver-exposed examples:')
            for line in examples:
                self.stdout.write(f'  {line}')
        verb = 'checked (dry run, nothing saved)' if options['dry_run'] else 'checked and saved'
        self.stdout.write(self.style.SUCCESS(f'\n{processed} files {verb}'))
