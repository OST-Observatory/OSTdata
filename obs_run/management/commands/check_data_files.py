from django.core.management.base import BaseCommand

from obs_run.file_check import check_data_files

FILE_KINDS = ('fits', 'ser', 'video', 'other')


class Command(BaseCommand):
    help = (
        'Check data files for truncated/unreadable files (errors) and non-compliant headers (warnings). '
        'Results are stored per file and listed on the admin maintenance page ("File integrity").'
    )

    def add_arguments(self, parser):
        parser.add_argument('--only-unchecked', action='store_true', help='Skip files checked before')
        parser.add_argument('--only-issues', action='store_true',
                            help='Re-check only files whose last check found errors or warnings')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of files to check')
        parser.add_argument(
            '--kind', choices=FILE_KINDS, action='append',
            help='File kinds to check (repeatable; default: all)',
        )

    def handle(self, *args, **options):
        summary = check_data_files(
            only_unchecked=options['only_unchecked'],
            only_issues=options['only_issues'],
            limit=options['limit'],
            kinds=options['kind'],
            progress=lambda checked: self.stdout.write(f'  {checked} files checked ...'),
        )
        self.stdout.write(self.style.SUCCESS(
            f"{summary['checked']} files checked: {summary['with_errors']} with errors, "
            f"{summary['with_warnings']} with warnings only"
        ))
