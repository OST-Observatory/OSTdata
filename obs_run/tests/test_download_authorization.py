"""Authorization tests for sync ZIP (gone) and async download jobs."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DataFile, ObservationRun

User = get_user_model()


class RunDownloadAuthorizationTest(APITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.public_run = ObservationRun.objects.create(name='Public Run', is_public=True)
        self.private_run = ObservationRun.objects.create(name='Private Run', is_public=False)
        self.authorized = User.objects.create_user(username='reader', password='reader-pass')
        self.other = User.objects.create_user(username='other', password='other-pass')
        self.private_run.readonly_users.add(self.authorized)
        path = Path(self.tmp) / 'f.fits'
        path.write_bytes(b'SIMPLE  ')
        self.df = DataFile.objects.create(
            observation_run=self.private_run,
            datafile=str(path),
            file_type='FITS',
            file_size=8,
        )
        self.public_url = f'/api/runs/runs/{self.public_run.pk}/download/'
        self.private_url = f'/api/runs/runs/{self.private_run.pk}/download/'
        self.public_job_url = f'/api/runs/runs/{self.public_run.pk}/download-jobs/'
        self.private_job_url = f'/api/runs/runs/{self.private_run.pk}/download-jobs/'
        self.client.get('/api/users/auth/csrf/')

    def _auth(self, user):
        self.client.force_login(user)

    def _csrf(self):
        token = self.client.cookies.get('csrftoken')
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    def test_sync_zip_is_gone(self):
        resp = self.client.get(self.private_url)
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)
        resp2 = self.client.get(self.public_url)
        self.assertEqual(resp2.status_code, status.HTTP_410_GONE)

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_unauthorized_user_private_download_job_denied(self, _delay):
        self._auth(self.other)
        resp = self.client.post(self.private_job_url, {'ids': [self.df.pk]}, format='json', **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        _delay.assert_not_called()

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_authorized_user_private_download_job_allowed(self, delay):
        self._auth(self.authorized)
        resp = self.client.post(self.private_job_url, {'ids': [self.df.pk]}, format='json', **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        delay.assert_called_once()


class VisibilityQueryTest(APITestCase):
    def setUp(self):
        self.public_run = ObservationRun.objects.create(name='Pub', is_public=True)
        self.private_run = ObservationRun.objects.create(name='Priv', is_public=False)
        self.user = User.objects.create_user(username='mix', password='mix-pass')
        self.private_run.readonly_users.add(self.user)
        self.tmp_dir = tempfile.mkdtemp()
        public_path = Path(self.tmp_dir) / 'public.fits'
        private_path = Path(self.tmp_dir) / 'private.fits'
        public_path.write_bytes(b'SIMPLE  ')
        private_path.write_bytes(b'SIMPLE  ')
        DataFile.objects.create(
            observation_run=self.public_run,
            datafile=str(public_path),
            file_type='FITS',
        )
        DataFile.objects.create(
            observation_run=self.private_run,
            datafile=str(private_path),
            file_type='FITS',
        )

    def test_logged_in_user_sees_public_and_private_files(self):
        from ostdata.custom_permissions import get_allowed_run_objects_to_view_for_user

        qs = get_allowed_run_objects_to_view_for_user(DataFile.objects.all(), self.user)
        paths = set(qs.values_list('datafile', flat=True))
        self.assertIn(str(Path(self.tmp_dir) / 'public.fits'), paths)
        self.assertIn(str(Path(self.tmp_dir) / 'private.fits'), paths)
