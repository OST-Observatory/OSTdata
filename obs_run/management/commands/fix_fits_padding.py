from django.core.management.base import BaseCommand

from obs_run.fits_padding import fix_fits_padding


class Command(BaseCommand):
    help = (
        'Append the missing padding of the last 2880-byte block to FITS files flagged by the file '
        'integrity check ("Last FITS block not padded"). Image data stay unchanged; size and hash are '
        'updated. Run check_data_files first to find such files.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only list the files that would be padded')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of files')

    def handle(self, *args, **options):
        results = fix_fits_padding(dry_run=options['dry_run'], limit=options['limit'])
        if not results:
            self.stdout.write('No files with missing FITS padding (run check_data_files first).')
            return
        for result in results:
            self.stdout.write(f"  #{result['pk']} {result['path']}: {result['status']} ({result['missing']} bytes)")
        counts = {}
        for result in results:
            key = result['status'].split(':')[0]
            counts[key] = counts.get(key, 0) + 1
        summary = ', '.join(f'{count} {status}' for status, count in sorted(counts.items()))
        self.stdout.write(self.style.SUCCESS(f'{len(results)} files: {summary}'))
