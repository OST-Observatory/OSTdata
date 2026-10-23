"""main_target_override: manual targets survive header re-analysis and object re-evaluation."""
import importlib
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APITestCase

from objects.models import Object
from obs_run.analyze_fits_header import analyze_fits
from obs_run.models import DataFile, ObservationRun
from ostdata.history_reason import REASON_ADMIN_LINK_DATAFILES, save_with_reason
from users.models import User
from utilities import evaluate_data_file, propagate_object_name_to_datafiles

HEADER = {'objectname': 'M42_field', 'imagetyp': 'Light', 'naxis1': 100, 'naxis2': 100}


class MainTargetOverrideTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-10-01', is_public=True)
        self.obj = Object.objects.create(name='M 42', is_public=True, object_type='GA')

    def _file(self, **kwargs):
        defaults = {'main_target': 'M 42', 'header_target_name': 'M42_field', 'exposure_type': 'LI'}
        return DataFile.objects.create(
            observation_run=self.run, datafile=f'/tmp/{DataFile.objects.count()}.fits', file_type='FITS',
            **{**defaults, **kwargs},
        )

    def _analyze(self, datafile, header):
        with patch.object(DataFile, 'get_fits_header', return_value={}), \
                patch('obs_run.analyze_fits_header.extract_fits_header_info', return_value=header):
            analyze_fits(datafile)
        datafile.refresh_from_db()

    def test_header_analysis_keeps_manual_target(self):
        datafile = self._file(main_target_override=True)
        self._analyze(datafile, {**HEADER, 'objectname': 'Orion'})
        self.assertEqual(datafile.main_target, 'M 42')
        self.assertEqual(datafile.header_target_name, 'Orion')

    def test_header_analysis_sets_target_without_override(self):
        datafile = self._file()
        self._analyze(datafile, {**HEADER, 'objectname': 'Orion'})
        self.assertEqual((datafile.main_target, datafile.header_target_name), ('Orion', 'Orion'))

    def test_re_evaluation_keeps_manual_association(self):
        datafile = self._file(main_target_override=True)
        self.obj.datafiles.add(datafile)
        with patch.object(DataFile, 'set_info'):
            result = evaluate_data_file(datafile, self.run)
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['skipped_reason'], 'datafile_target_override')
        self.assertEqual(list(datafile.object_set.values_list('pk', flat=True)), [self.obj.pk])

    def test_object_rename_reaches_manually_linked_files(self):
        datafile = self._file(main_target_override=True)
        self.obj.datafiles.add(datafile)
        self.obj.name = 'Orion Nebula'
        self.obj.save()
        propagate_object_name_to_datafiles(self.obj)
        datafile.refresh_from_db()
        self.assertEqual(datafile.main_target, 'Orion Nebula')

    def test_migration_flags_files_linked_by_hand(self):
        manual = self._file()
        save_with_reason(manual, REASON_ADMIN_LINK_DATAFILES)
        automatic = self._file()
        DataFile.objects.update(main_target_override=False)

        migration = importlib.import_module('obs_run.migrations.0018_datafile_main_target_override')
        migration.flag_manually_linked_files(apps, None)

        self.assertTrue(DataFile.objects.get(pk=manual.pk).main_target_override)
        self.assertFalse(DataFile.objects.get(pk=automatic.pk).main_target_override)


class AdminLinkSetsOverrideTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-10-02', is_public=True)
        self.obj = Object.objects.create(name='M 42', is_public=True, object_type='GA')
        self.datafile = DataFile.objects.create(
            observation_run=self.run, datafile='/tmp/link.fits', file_type='FITS',
            main_target='Orion', header_target_name='M42_field', exposure_type='LI',
        )
        self.client.get('/api/users/auth/csrf/')
        self.client.force_login(User.objects.create_superuser(username='admin', password='pw'))

    def _post(self, url, payload):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        headers = {'HTTP_X_CSRFTOKEN': token.value} if token else {}
        response = self.client.post(url, payload, format='json', **headers)
        self.assertEqual(response.status_code, 200, response.content)

    def test_link_and_unlink_set_manual_target(self):
        self._post('/api/admin/datafiles/link-objects/', {'datafile_ids': [self.datafile.pk], 'object_id': self.obj.pk})
        self.datafile.refresh_from_db()
        self.assertEqual((self.datafile.main_target, self.datafile.main_target_override), ('M 42', True))

        self._post('/api/admin/datafiles/unlink-objects/', {'datafile_ids': [self.datafile.pk]})
        self.datafile.refresh_from_db()
        self.assertEqual((self.datafile.main_target, self.datafile.main_target_override), ('M42_field', True))
        self.assertFalse(self.datafile.object_set.exists())

        response = self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/')
        self.assertTrue(response.json()['main_target_override'])
