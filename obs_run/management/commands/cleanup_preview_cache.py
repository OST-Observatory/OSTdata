from django.core.management.base import BaseCommand

from obs_run.preview_cache import cache_status, cleanup_cache


def _mb(value):
    return f'{(value or 0) / 1024 / 1024:.1f} MB'


class Command(BaseCommand):
    help = (
        'Remove cached previews (sky view images, video thumbnails) unused for --max-age-days, of deleted '
        'or changed files, and outdated formats. They are re-rendered on demand.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--max-age-days', type=int, default=None,
                            help='Remove previews unused for this many days (default: PREVIEW_CACHE_MAX_AGE_DAYS)')
        parser.add_argument('--dry-run', action='store_true', help='Only show what would be removed')

    def handle(self, *args, **options):
        before = cache_status()
        summary = cleanup_cache(max_age_days=options['max_age_days'], dry_run=options['dry_run'])
        verb = 'would remove' if summary['dry_run'] else 'removed'
        self.stdout.write(f"Cache before: {before['total_files']} files, {_mb(before['total_bytes'])}")
        self.stdout.write(
            f"{verb} {summary['removed_files']} files ({_mb(summary['removed_bytes'])}), "
            f"unused for {summary['max_age_days']} days or more: {summary['reasons']}"
        )
