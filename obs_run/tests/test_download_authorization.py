"""Tests for run download authorization (audit remediation)."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from obs_run.models import DataFile, ObservationRun

User = get_user_model()


class RunDownloadAuthorizationTest(APITestCase):
    def setUp(self):
        self.public_run = ObservationRun.objects.create(name='Public Run', is_public=True)
        self.private_run = ObservationRun.objects.create(name='Private Run', is_public=False)
        self.authorized = User.objects.create_user(username='reader', password='reader-pass')
        self.other = User.objects.create_user(username='other', password='other-pass')
        self.private_run.readonly_users.add(self.authorized)
        self.public_url = f'/api/runs/runs/{self.public_run.pk}/download/'
        self.private_url = f'/api/runs/runs/{self.private_run.pk}/download/'
        self.public_job_url = f'/api/runs/runs/{self.public_run.pk}/download-jobs/'
        self.private_job_url = f'/api/runs/runs/{self.private_run.pk}/download-jobs/'

    def _auth(self, user):
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_anonymous_private_run_download_denied(self):
        resp = self.client.get(self.private_url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_public_run_download_allowed_without_files(self):
        resp = self.client.get(self.public_url)
        self.assertIn(resp.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK))

    def test_unauthorized_user_private_run_download_denied(self):
        self._auth(self.other)
        resp = self.client.get(self.private_url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_authorized_user_private_run_download_not_denied(self):
        self._auth(self.authorized)
        resp = self.client.get(self.private_url)
        self.assertNotEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_unauthorized_user_private_download_job_denied(self, _delay):
        self._auth(self.other)
        resp = self.client.post(self.private_job_url, {'ids': []}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        _delay.assert_not_called()

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_authorized_user_private_download_job_allowed(self, delay):
        self._auth(self.authorized)
        resp = self.client.post(self.private_job_url, {'ids': []}, format='json')
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
