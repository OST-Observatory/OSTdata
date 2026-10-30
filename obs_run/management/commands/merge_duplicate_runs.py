from django.core.management.base import BaseCommand

from obs_run.run_merge import merge_duplicate_runs


class Command(BaseCommand):
    help = (
        'Merge observation runs with the same name into the oldest one (data files, download jobs, object '
        'links, permissions and tags are moved). Without --apply only shows what would be done. Needed '
        'before the migration that makes run names unique.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Merge (default: dry run)')

    def handle(self, *args, **options):
        dry_run = not options['apply']
        reports = merge_duplicate_runs(dry_run=dry_run)
        if not reports:
            self.stdout.write(self.style.SUCCESS('No duplicate run names.'))
            return
        for report in reports:
            self.stdout.write(
                f"{report['name']}: keep #{report['keep']}, merge {['#%s' % pk for pk in report['merge']]} "
                f"({report['datafiles']} files, {report['download_jobs']} download jobs, "
                f"{report['objects']} object links)"
            )
            for difference in report['differences']:
                self.stdout.write(self.style.WARNING(f'    differs, kept value of #{report["keep"]}: {difference}'))
        verb = 'would be merged' if dry_run else 'merged'
        self.stdout.write(self.style.SUCCESS(f'{len(reports)} run names {verb}.'))
        if dry_run:
            self.stdout.write('Run again with --apply to merge.')
