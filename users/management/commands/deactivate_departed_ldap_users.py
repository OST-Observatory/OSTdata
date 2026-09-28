from django.core.management.base import BaseCommand, CommandError

from users.departed import LdapUnavailable, SafetyStop, run_departed_check


class Command(BaseCommand):
    help = (
        'Deactivate accounts whose LDAP entry is gone and clear their name and e-mail '
        '(runs daily via Celery beat; any LDAP error aborts without changes).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--force',
            action='store_true',
            help='Apply even if more than half of the LDAP accounts would be deactivated.',
        )

    def handle(self, *args, **options):
        try:
            result = run_departed_check(dry_run=options['dry_run'], force=options['force'])
        except (LdapUnavailable, SafetyStop) as exc:
            raise CommandError(f'{exc} — no accounts were changed.') from exc
        if result is None:
            self.stdout.write('LDAP is not configured; nothing to check.')
            return
        verb = 'Would deactivate' if options['dry_run'] else 'Deactivated'
        names = ', '.join(result.departed) or 'none'
        self.stdout.write(self.style.SUCCESS(
            f'Checked {result.checked} LDAP account(s). {verb} {len(result.departed)}: {names}'
        ))
