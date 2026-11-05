from collections import Counter

from django.core.management.base import BaseCommand

from obs_run.spectrograph_heuristics import apply_agreed_suggestions


class Command(BaseCommand):
    help = (
        'Apply the stored spectrograph suggestions on which run majority and path token agree (files without '
        'a manual spectrograph; spectrograph rules take precedence). Run compute_spectrograph_suggestions first.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only list what would change')
        parser.add_argument('--list', action='store_true', help='Print every affected file')

    def handle(self, *args, **options):
        changes = apply_agreed_suggestions(dry_run=options['dry_run'])
        if options['list']:
            for pk, old, new, path in changes:
                self.stdout.write(f'  {pk:>8}  {old} -> {new}  {path}')
        for change, count in Counter(f'{old} -> {new}' for _, old, new, _ in changes).most_common():
            self.stdout.write(f'  {count:>8}  {change}')
        verb = 'would change (dry run)' if options['dry_run'] else 'changed'
        self.stdout.write(self.style.SUCCESS(f'{len(changes)} files {verb}'))
