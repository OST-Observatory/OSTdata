"""Smoke test for async download job enqueue (mocked Celery)."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DownloadJob, ObservationRun

User = get_user_model()


class DownloadJobFlowTest(APITestCase):
    @patch('obs_run.services.downloads.build_zip_task.delay')
    def test_enqueue_status_flow(self, delay):
        user = User.objects.create_user(username='dluser', password='pass')
        run = ObservationRun.objects.create(name='Pub', is_public=True)
        self.client.force_login(user)

        create_resp = self.client.post(
            f'/api/runs/runs/{run.pk}/download-jobs/',
            {'ids': [], 'filters': {}},
            format='json',
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        job_id = create_resp.data['job_id']
        delay.assert_called_once_with(job_id)

        status_resp = self.client.get(f'/api/runs/jobs/{job_id}/status')
        self.assertEqual(status_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(status_resp.data['status'], 'queued')
        self.assertTrue(DownloadJob.objects.filter(pk=job_id, user=user).exists())
