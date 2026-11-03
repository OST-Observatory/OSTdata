from django.core.management.base import BaseCommand

from obs_run.datafile_merge import merge_duplicate_datafiles


class Command(BaseCommand):
    help = (
        'Merge data file entries with the same path into one (object links, plate solving failures and '
        'manual values are kept). Without --apply only shows what would be done. Needed before the '
        'migration that makes data file paths unique.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Merge (default: dry run)')

    def handle(self, *args, **options):
        dry_run = not options['apply']
        reports = merge_duplicate_datafiles(dry_run=dry_run)
        if not reports:
            self.stdout.write(self.style.SUCCESS('No duplicate data file paths.'))
            return
        for report in reports:
            self.stdout.write(
                f"{report['path']}: keep #{report['keep']}, merge {['#%s' % pk for pk in report['merge']]} "
                f"({report['objects']} additional object links)"
            )
            for copied in report['copied']:
                self.stdout.write(self.style.WARNING(f'    copied to #{report["keep"]}: {copied}'))
        verb = 'would be merged' if dry_run else 'merged'
        self.stdout.write(self.style.SUCCESS(f'{len(reports)} duplicate paths {verb}.'))
        if dry_run:
            self.stdout.write('Run again with --apply to merge.')
