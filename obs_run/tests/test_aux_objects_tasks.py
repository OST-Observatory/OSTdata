"""Tests for Celery auxiliary-object tasks."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.aux_objects import mark_aux_objects_pending
from obs_run.models import DataFile, ObservationRun
from obs_run.tasks import enqueue_aux_objects_for_run, process_aux_objects_queue

User = get_user_model()


@override_settings(
    AUX_OBJECTS_ENABLED=True,
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class AuxObjectsTasksTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2024_aux_task', is_public=True, photometry=True)
        self.df = DataFile.objects.create(
            observation_run=self.run,
            datafile='light.fits',
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            plate_solved=True,
            wcs_ra=10.0,
            wcs_dec=20.0,
            fov_x=0.5,
            fov_y=0.4,
            ra=10.0,
            dec=20.0,
        )

    @patch('obs_run.aux_objects.wait_for_aux_simbad_query_slot')
    @patch('obs_run.aux_objects._query_region_safe')
    @patch('obs_run.aux_objects.filter_table_to_footprint', side_effect=lambda t, _df: t)
    def test_enqueue_aux_objects_for_run(self, _filter_mock, query_mock, wait_mock):
        from astropy.table import Table
        query_mock.return_value = Table({'main_id': ['HD 1'], 'ra': [10.0], 'dec': [20.0], 'alltypes.otypes': ['*']})

        ok = enqueue_aux_objects_for_run(self.run.pk, force=True)
        self.assertTrue(ok)
        self.run.refresh_from_db()
        self.assertEqual(self.run.aux_objects_status, ObservationRun.AUX_STATUS_READY)
        self.assertEqual(len(self.run.aux_objects), 1)
        wait_mock.assert_called()

    @patch('obs_run.tasks.enqueue_aux_objects_for_run', return_value=True)
    def test_process_aux_objects_queue(self, enqueue_mock):
        result = process_aux_objects_queue()
        self.assertGreaterEqual(result.get('enqueued', 0), 0)
        enqueue_mock.assert_called()


@override_settings(AUX_OBJECTS_ENABLED=True, CELERY_TASK_ALWAYS_EAGER=True)
class AuxObjectsAdminApiTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='auxadmin', password='x', is_staff=True, is_superuser=True)
        self.client.force_authenticate(user=self.admin)
        self.run = ObservationRun.objects.create(name='2024_admin_aux', is_public=True, photometry=True)
        DataFile.objects.create(
            observation_run=self.run,
            datafile='light.fits',
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            plate_solved=True,
            wcs_ra=10.0,
            wcs_dec=20.0,
            fov_x=0.5,
            fov_y=0.4,
        )

    def test_admin_stats(self):
        response = self.client.get('/api/admin/runs/aux-objects/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('missing', response.data)
        self.assertTrue(response.data.get('enabled'))

    @patch('adminops.api.views.enqueue_aux_objects_for_run', return_value=True)
    def test_admin_trigger_missing(self, enqueue_mock):
        response = self.client.post(
            '/api/admin/runs/aux-objects/trigger/',
            {'mode': 'missing', 'require_wcs': True, 'force': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['enqueued'], 1)
        enqueue_mock.assert_called_once()

    @patch('adminops.api.views.process_aux_objects_queue')
    def test_admin_trigger_queue(self, queue_mock):
        queue_mock.delay.return_value = type('R', (), {'id': 'task-1'})()
        response = self.client.post('/api/admin/runs/aux-objects/queue/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(response.data.get('enqueued'))
        queue_mock.delay.assert_called_once()


@override_settings(AUX_OBJECTS_ENABLED=False, CELERY_TASK_ALWAYS_EAGER=True)
class AuxObjectsAdminDisabledTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='auxadmin2', password='x', is_staff=True, is_superuser=True)
        self.client.force_authenticate(user=self.admin)

    def test_admin_stats_reports_disabled(self):
        response = self.client.get('/api/admin/runs/aux-objects/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data.get('enabled'))

    def test_admin_trigger_rejected_when_disabled(self):
        response = self.client.post(
            '/api/admin/runs/aux-objects/trigger/',
            {'mode': 'all', 'require_wcs': True, 'force': True},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('AUX_OBJECTS_ENABLED', response.data.get('detail', ''))


@override_settings(AUX_OBJECTS_ENABLED=False, CELERY_TASK_ALWAYS_EAGER=True)
class AuxObjectsAdminNoPermTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='auxnoperm', password='x', is_staff=True)
        self.client.force_authenticate(user=self.user)

    def test_admin_queue_forbidden_without_acl(self):
        response = self.client.post('/api/admin/runs/aux-objects/queue/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('acl_runs_aux_objects_admin', response.data.get('detail', ''))
