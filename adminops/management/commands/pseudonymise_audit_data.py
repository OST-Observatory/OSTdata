from django.core.management.base import BaseCommand

from adminops.retention import pseudonymise_personal_data


class Command(BaseCommand):
    help = (
        'Remove the acting user from change-history and audit-log entries older than '
        'PERSONAL_DATA_RETENTION_DAYS (runs daily via Celery beat; use --dry-run to preview).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None, help='Override PERSONAL_DATA_RETENTION_DAYS.')
        parser.add_argument('--dry-run', action='store_true', help='Only count, change nothing.')

    def handle(self, *args, **options):
        result = pseudonymise_personal_data(days=options['days'], dry_run=options['dry_run'])
        prefix = 'Would pseudonymise' if result['dry_run'] else 'Pseudonymised'
        self.stdout.write(f"Cutoff: {result['cutoff']}")
        for label, count in sorted(result['history'].items()):
            self.stdout.write(f'  {label}: {count}')
        self.stdout.write(f"  adminops.AuditLogEntry (user): {result['audit_log']}")
        self.stdout.write(f"  adminops.AuditLogEntry (user_role details): {result['user_role']}")
        self.stdout.write(self.style.SUCCESS(f'{prefix} entries older than the cutoff.'))
