from django.core.management.base import BaseCommand

from users.api.views import _acl_bootstrap


class Command(BaseCommand):
    help = 'Bootstrap ACL permissions and add missing staff-group defaults (non-destructive).'

    def handle(self, *args, **options):
        _acl_bootstrap()
        self.stdout.write(self.style.SUCCESS('ACL permissions synced; staff group updated with any missing defaults.'))
