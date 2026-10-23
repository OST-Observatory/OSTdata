"""File integrity check: truncated/missing files, storage without history, command and admin API."""
import struct
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run.file_check import check_datafile, update_file_issues
from obs_run.models import DataFile, ObservationRun
from users.models import User


def _ser_bytes(frames_declared, frames_written, width=10, height=10):
    """8-bit mono SER file: 178-byte header + frames."""
    header = struct.pack(
        '<14s 7i 40s 40s 40s 2q', b'LUCAM-RECORDER', 0, 0, 1, width, height, 8, frames_declared,
        b'', b'', b'', 0, 0,
    )
    return header + bytes(width * height * frames_written)


class FileCheckTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run = ObservationRun.objects.create(name='2026-10-07', is_public=True)

    def _file(self, name, file_type, content=None):
        path = self.tmp / name
        if content is not None:
            path.write_bytes(content)
        return DataFile.objects.create(observation_run=self.run, datafile=str(path), file_type=file_type)

    def _fits(self, name, truncate_by=0):
        path = self.tmp / name
        fits.PrimaryHDU(np.zeros((100, 100), dtype=np.int16)).writeto(path)
        if truncate_by:
            data = path.read_bytes()
            path.write_bytes(data[:-truncate_by])
        return DataFile.objects.create(observation_run=self.run, datafile=str(path), file_type='FITS')

    def test_fits(self):
        self.assertEqual(check_datafile(self._fits('ok.fits')), [])
        issues = check_datafile(self._fits('cut.fits', truncate_by=4000))
        self.assertIn('error', {issue['level'] for issue in issues})

    def test_missing_file(self):
        self.assertEqual(check_datafile(self._file('gone.fits', 'FITS')), [
            {'level': 'error', 'message': 'File missing on disk'},
        ])

    def test_ser(self):
        self.assertEqual(check_datafile(self._file('ok.ser', 'SER', _ser_bytes(5, 5))), [])
        issues = check_datafile(self._file('cut.ser', 'SER', _ser_bytes(5, 2)))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['level'], 'error')
        self.assertIn('2 of 5 frames complete', issues[0]['message'])

    def test_result_stored_without_history_entry(self):
        datafile = self._file('cut2.ser', 'SER', _ser_bytes(5, 1))
        history_count = datafile.history.count()
        update_file_issues(datafile)
        datafile.refresh_from_db()
        self.assertEqual(datafile.file_issue_level, 'error')
        self.assertIsNotNone(datafile.file_issues_checked_at)
        self.assertEqual(datafile.history.count(), history_count)

    def test_command(self):
        self._file('ok2.ser', 'SER', _ser_bytes(3, 3))
        self._file('gone2.fits', 'FITS')
        out = StringIO()
        call_command('check_data_files', stdout=out)
        self.assertIn('2 files checked: 1 with errors, 0 with warnings only', out.getvalue())
        out = StringIO()
        call_command('check_data_files', '--only-unchecked', stdout=out)
        self.assertIn('0 files checked', out.getvalue())


class FileIssuesApiTest(APITestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='2026-10-08', is_public=True)
        self.broken = DataFile.objects.create(
            observation_run=run, datafile='/data/run/broken.fits', file_type='FITS',
            file_issues=[{'level': 'error', 'message': 'File may have been truncated'}], file_issue_level='error',
        )
        DataFile.objects.create(
            observation_run=run, datafile='/data/run/odd.fits', file_type='FITS',
            file_issues=[{'level': 'warning', 'message': 'Unparsable card'}], file_issue_level='warning',
        )
        DataFile.objects.create(observation_run=run, datafile='/data/run/fine.fits', file_type='FITS')
        self.client.get('/api/users/auth/csrf/')

    def _headers(self):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    def test_list_requires_maintenance_permission(self):
        self.client.force_login(User.objects.create_user(username='reader', password='pw'))
        self.assertEqual(self.client.get('/api/admin/maintenance/file-issues/').status_code, 403)

    def test_list_and_trigger(self):
        self.client.force_login(User.objects.create_superuser(username='admin', password='pw'))
        data = self.client.get('/api/admin/maintenance/file-issues/').json()
        self.assertEqual((data['counts']['error'], data['counts']['warning'], data['count']), (1, 1, 2))
        self.assertEqual(data['results'][0]['pk'], self.broken.pk)  # errors first

        data = self.client.get('/api/admin/maintenance/file-issues/', {'level': 'warning'}).json()
        self.assertEqual([row['file_name'] for row in data['results']], ['odd.fits'])

        with patch('adminops.api.views._celery_delay') as delay:
            response = self.client.post(
                '/api/admin/maintenance/check-files/', {'only_unchecked': True}, format='json', **self._headers(),
            )
        self.assertEqual(response.status_code, 202, response.content)
        self.assertTrue(delay.call_args.kwargs['only_unchecked'])
