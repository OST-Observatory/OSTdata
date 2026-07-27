"""Role-matrix visibility / ACL regression tests."""
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase

from objects.models import Object
from obs_run.models import DataFile, ObservationRun
from users.api.acl_views import _ensure_acl_registry
from users.models import User as OstUser

User = get_user_model()


def _grant(user, codename: str):
    _ensure_acl_registry()
    ct = ContentType.objects.get_for_model(OstUser)
    perm = Permission.objects.get(content_type=ct, codename=codename)
    user.user_permissions.add(perm)


class VisibilityAclMatrixTest(APITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.public_run = ObservationRun.objects.create(name='PubRun', is_public=True)
        self.private_run = ObservationRun.objects.create(name='PrivRun', is_public=False)
        self.public_obj = Object.objects.create(name='PubObj', is_public=True, object_type='GA')
        self.private_obj = Object.objects.create(name='PrivObj', is_public=False, object_type='GA')
        self.public_obj.observation_run.add(self.public_run)
        self.private_obj.observation_run.add(self.private_run)

        pub_path = Path(self.tmp) / 'pub.fits'
        priv_path = Path(self.tmp) / 'priv.fits'
        pub_path.write_bytes(b'SIMPLE  ')
        priv_path.write_bytes(b'SIMPLE  ')
        self.pub_df = DataFile.objects.create(
            observation_run=self.public_run, datafile=str(pub_path), file_type='FITS', file_size=8
        )
        self.priv_df = DataFile.objects.create(
            observation_run=self.private_run, datafile=str(priv_path), file_type='FITS', file_size=8
        )
        self.public_obj.datafiles.add(self.pub_df)
        self.private_obj.datafiles.add(self.priv_df)

        self.outsider = User.objects.create_user(username='outsider', password='x')
        self.reader = User.objects.create_user(username='reader', password='x')
        self.private_run.readonly_users.add(self.reader)
        self.staff_no_acl = User.objects.create_user(username='staff', password='x', is_staff=True)
        self.superuser = User.objects.create_superuser(username='root', password='x', email='r@e.com')
        self.object_viewer = User.objects.create_user(username='objview', password='x')
        _grant(self.object_viewer, 'acl_objects_view_private')
        self.client.get('/api/users/auth/csrf/')

    def _csrf(self):
        token = self.client.cookies.get('csrftoken')
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    def test_anonymous_lists_only_public_runs(self):
        resp = self.client.get('/api/runs/runs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        if isinstance(results, dict):
            results = results.get('results', [])
        names = {r['name'] for r in results}
        self.assertIn('PubRun', names)
        self.assertNotIn('PrivRun', names)

    def test_outsider_cannot_retrieve_private_run(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(f'/api/runs/runs/{self.private_run.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_reader_can_retrieve_private_run(self):
        self.client.force_login(self.reader)
        resp = self.client.get(f'/api/runs/runs/{self.private_run.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_without_acl_cannot_see_private_run(self):
        self.client.force_login(self.staff_no_acl)
        resp = self.client.get(f'/api/runs/runs/{self.private_run.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_nested_object_runs_hide_private(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(f'/api/objects/{self.private_obj.pk}/observation_runs/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_login(self.object_viewer)
        resp = self.client.get(f'/api/objects/{self.private_obj.pk}/observation_runs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        names = {r['name'] for r in resp.data}
        self.assertNotIn('PrivRun', names)

    def test_observing_conditions_private_404(self):
        resp = self.client.get(f'/api/runs/runs/{self.private_run.pk}/conditions/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_datafile_serializer_omits_absolute_path(self):
        resp = self.client.get(f'/api/runs/datafiles/{self.pub_df.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('file_path', resp.data)
        self.assertEqual(resp.data.get('file_name'), 'pub.fits')
        self.assertIn('download_url', resp.data)

    def test_create_run_requires_acl(self):
        self.client.force_login(self.outsider)
        resp = self.client.post('/api/runs/runs/', {'name': 'Nope'}, format='json', **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
