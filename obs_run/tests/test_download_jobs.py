"""Smoke and security tests for async download jobs."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DataFile, DownloadJob, ObservationRun
from obs_run.services.downloads import hash_download_token

User = get_user_model()


class DownloadJobFlowTest(APITestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.run = ObservationRun.objects.create(name='Pub', is_public=True)
        path = Path(self.tmp) / 'a.fits'
        path.write_bytes(b'SIMPLE  ')
        self.df = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(path),
            file_type='FITS',
            file_size=8,
        )
        self.client.get('/api/users/auth/csrf/')

    def _csrf(self):
        token = self.client.cookies.get('csrftoken')
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_enqueue_status_flow(self, delay):
        user = User.objects.create_user(username='dluser', password='pass')
        self.client.force_login(user)

        create_resp = self.client.post(
            f'/api/runs/runs/{self.run.pk}/download-jobs/',
            {'ids': [self.df.pk], 'filters': {}},
            format='json',
            **self._csrf(),
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        job_id = create_resp.data['job_id']
        self.assertNotIn('job_token', create_resp.data)
        delay.assert_called_once_with(job_id)

        status_resp = self.client.get(f'/api/runs/jobs/{job_id}/status')
        self.assertEqual(status_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(status_resp.data['status'], 'queued')
        self.assertTrue(DownloadJob.objects.filter(pk=job_id, user=user).exists())

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_anonymous_job_requires_token(self, delay):
        create_resp = self.client.post(
            f'/api/runs/runs/{self.run.pk}/download-jobs/',
            {'ids': [self.df.pk], 'filters': {}},
            format='json',
            **self._csrf(),
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        job_id = create_resp.data['job_id']
        token = create_resp.data.get('job_token')
        self.assertTrue(token)
        job = DownloadJob.objects.get(pk=job_id)
        self.assertEqual(job.access_token_hash, hash_download_token(token))
        self.assertNotEqual(job.access_token_hash, token)

        denied = self.client.get(f'/api/runs/jobs/{job_id}/status')
        self.assertEqual(denied.status_code, status.HTTP_404_NOT_FOUND)

        wrong = self.client.get(
            f'/api/runs/jobs/{job_id}/status',
            HTTP_X_DOWNLOAD_TOKEN='wrong-token',
        )
        self.assertEqual(wrong.status_code, status.HTTP_404_NOT_FOUND)

        ok = self.client.get(
            f'/api/runs/jobs/{job_id}/status',
            HTTP_X_DOWNLOAD_TOKEN=token,
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_empty_bulk_without_filters_rejected(self, delay):
        resp = self.client.post(
            '/api/runs/datafiles/download-jobs/',
            {'ids': [], 'filters': {}},
            format='json',
            **self._csrf(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        delay.assert_not_called()

    @patch('obs_run.services.downloads.build_zip_task.delay')
    @override_settings(DOWNLOAD_JOB_MAX_FILES=0)
    def test_quota_max_files(self, delay):
        resp = self.client.post(
            f'/api/runs/runs/{self.run.pk}/download-jobs/',
            {'ids': [self.df.pk], 'filters': {}},
            format='json',
            **self._csrf(),
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        delay.assert_not_called()

    def test_sync_zip_routes_gone(self):
        resp = self.client.get(f'/api/runs/runs/{self.run.pk}/download/')
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)
        resp2 = self.client.get('/api/runs/datafiles/download/')
        self.assertEqual(resp2.status_code, status.HTTP_410_GONE)

    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_other_user_cannot_access_owned_job(self, delay):
        owner = User.objects.create_user(username='owner', password='pass')
        other = User.objects.create_user(username='intruder', password='pass')
        self.client.force_login(owner)
        create_resp = self.client.post(
            f'/api/runs/runs/{self.run.pk}/download-jobs/',
            {'ids': [self.df.pk]},
            format='json',
            **self._csrf(),
        )
        job_id = create_resp.data['job_id']
        self.client.force_login(other)
        resp = self.client.get(f'/api/runs/jobs/{job_id}/status')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
