"""User permission model tests."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from obs_run.models import ObservationRun
from ostdata.permissions import HasPerm, user_has_acl

User = get_user_model()


class UserRunPermissionTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='Private', is_public=False)
        self.reader = User.objects.create_user(username='reader', password='x')
        self.writer = User.objects.create_user(username='writer', password='x')
        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.run.readonly_users.add(self.reader)
        self.run.readwrite_users.add(self.writer)

    def test_can_read_public_for_everyone(self):
        self.run.is_public = True
        self.run.save(update_fields=['is_public'])
        self.assertTrue(self.outsider.can_read(self.run))

    def test_can_read_private_only_for_members(self):
        self.assertTrue(self.reader.can_read(self.run))
        self.assertTrue(self.writer.can_read(self.run))
        self.assertFalse(self.outsider.can_read(self.run))

    def test_can_add_requires_write_membership(self):
        self.assertFalse(self.reader.can_add(self.run))
        self.assertTrue(self.writer.can_add(self.run))

    def test_can_edit_requires_write_membership(self):
        class _RunSubject:
            pass

        subject = _RunSubject()
        subject.observation_run = self.run
        self.assertFalse(self.reader.can_edit(subject))
        self.assertTrue(self.writer.can_edit(subject))


class AclPermissionFactoryTest(TestCase):
    def test_superuser_bypasses_acl(self):
        user = User.objects.create_superuser(username='root', password='x', email='r@example.com')
        self.assertTrue(user_has_acl(user, 'acl_users_delete'))

    def test_anonymous_has_no_acl(self):
        class Anonymous:
            is_authenticated = False
            is_superuser = False

        self.assertFalse(user_has_acl(Anonymous(), 'acl_users_view'))

    def test_has_perm_factory_superuser(self):
        Perm = HasPerm('acl_runs_delete')
        user = User.objects.create_superuser(username='admin', password='x', email='a@example.com')
        self.assertTrue(Perm().has_permission(type('R', (), {'user': user})(), None))
