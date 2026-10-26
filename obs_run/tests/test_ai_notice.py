"""Lab course AI notice: byte-exact header edit, which files get it, sync, admin API."""
import tempfile
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.time import Time
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from obs_run.ai_notice import (
    BLOCK,
    DEFAULT_TEXT,
    add_notice,
    has_notice,
    remove_notice,
    should_have_notice,
    sync_notice,
    sync_notices,
)
from obs_run.models import DataFile, ObservationRun
from users.models import User
from utilities import compute_file_hash

NOW_JD = Time.now().jd


def _write_fits(path, extra_cards=0, null_padding=False):
    hdu = fits.PrimaryHDU(np.arange(10000, dtype=np.int16).reshape(100, 100))
    hdu.header['OBJECT'] = 'Vega'
    for index in range(extra_cards):
        hdu.header[f'KEY{index:04d}'] = index
    hdu.writeto(path)
    if null_padding:
        # Non-compliant files: NUL bytes instead of spaces after END
        raw = bytearray(path.read_bytes())
        end = raw.find(b'END' + b' ' * 77)
        header_length = (end // BLOCK + 1) * BLOCK
        raw[end + 80:header_length] = b'\x00' * (header_length - end - 80)
        path.write_bytes(bytes(raw))
    return path


class HeaderEditTest(TestCase):
    def test_round_trip_restores_the_original_bytes(self):
        # 27 extra cards fill the header block: the notice needs an additional block
        for name, extra_cards, null_padding in (('room', 0, False), ('full', 27, False), ('nul', 0, True)):
            with self.subTest(case=name):
                path = _write_fits(Path(tempfile.mkdtemp()) / f'{name}.fits', extra_cards, null_padding)
                original = path.read_bytes()
                with fits.open(path, do_not_scale_image_data=True) as hdul:
                    data = hdul[0].data.copy()

                self.assertTrue(add_notice(path, DEFAULT_TEXT))
                self.assertFalse(add_notice(path, DEFAULT_TEXT))  # only once
                with fits.open(path, do_not_scale_image_data=True) as hdul:
                    self.assertEqual(hdul[0].header['AINOTICE'], DEFAULT_TEXT)
                    self.assertEqual(hdul[0].header['OBJECT'], 'Vega')
                    np.testing.assert_array_equal(hdul[0].data, data)

                self.assertTrue(remove_notice(path))
                self.assertFalse(has_notice(path))
                self.assertEqual(path.read_bytes(), original)


@override_settings(AI_NOTICE_ENABLED=True, AI_NOTICE_DAYS=183, AI_NOTICE_SINCE='', AI_NOTICE_TEXT='')
class NoticeRulesTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run = ObservationRun.objects.create(name='2026-10-20', is_public=True)

    def _file(self, name='spec.fits', days_ago=10, spectrograph='D', **kwargs):
        path = _write_fits(self.tmp / name)
        return DataFile.objects.create(
            observation_run=self.run, datafile=str(path), file_type='FITS', exposure_type='LI',
            exposure_type_ml='LI', spectrograph=spectrograph, hjd=NOW_JD - days_ago, **kwargs,
        )

    def test_which_files_get_the_notice(self):
        self.assertTrue(should_have_notice(self._file('new.fits')))
        self.assertFalse(should_have_notice(self._file('old.fits', days_ago=400)))  # earlier semester
        self.assertFalse(should_have_notice(self._file('photometry.fits', spectrograph='N')))
        self.assertFalse(should_have_notice(self._file('exempt.fits', ai_notice_exempt=True)))
        with override_settings(AI_NOTICE_ENABLED=False):
            self.assertFalse(should_have_notice(self._file('off.fits')))
        since = Time(NOW_JD - 5, format='jd').to_datetime().date().isoformat()
        with override_settings(AI_NOTICE_SINCE=since):
            self.assertFalse(should_have_notice(self._file('before_start.fits', days_ago=10)))

    def test_sync_writes_and_removes_the_keyword(self):
        datafile = self._file()
        path = Path(datafile.datafile)
        original_hash = compute_file_hash(path)
        history_count = datafile.history.count()

        self.assertEqual(sync_notice(datafile), 'added')
        datafile.refresh_from_db()
        self.assertTrue(has_notice(path))
        self.assertIsNotNone(datafile.ai_notice_added_at)
        self.assertEqual(datafile.content_hash, compute_file_hash(path))
        self.assertIsNone(sync_notice(datafile))  # nothing to do

        # Half a year later the notice is removed and the original file restored
        DataFile.objects.filter(pk=datafile.pk).update(hjd=NOW_JD - 200)
        datafile.refresh_from_db()
        self.assertEqual(sync_notice(datafile), 'removed')
        datafile.refresh_from_db()
        self.assertFalse(has_notice(path))
        self.assertIsNone(datafile.ai_notice_added_at)
        self.assertEqual(datafile.content_hash, original_hash)
        self.assertEqual(datafile.history.count(), history_count)

    def test_switching_off_removes_existing_notices(self):
        datafile = self._file()
        self.assertEqual(sync_notices()['added'], 1)
        with override_settings(AI_NOTICE_ENABLED=False):
            self.assertEqual(sync_notices()['removed'], 1)
        self.assertFalse(has_notice(Path(datafile.datafile)))

    def test_write_error_is_stored(self):
        datafile = self._file()
        Path(datafile.datafile).unlink()
        self.assertIsNone(sync_notice(datafile))
        datafile.refresh_from_db()
        self.assertTrue(datafile.ai_notice_error)
        self.assertIsNone(datafile.ai_notice_added_at)


@override_settings(AI_NOTICE_ENABLED=True, AI_NOTICE_DAYS=183, AI_NOTICE_SINCE='', AI_NOTICE_TEXT='')
class AiNoticeApiTest(APITestCase):
    def setUp(self):
        path = _write_fits(Path(tempfile.mkdtemp()) / 'spec.fits')
        run = ObservationRun.objects.create(name='2026-10-21', is_public=True)
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(path), file_type='FITS', exposure_type='LI',
            exposure_type_ml='LI', spectrograph='B', hjd=NOW_JD - 3,
        )
        sync_notice(self.datafile)
        self.client.get('/api/users/auth/csrf/')

    def _post(self, url, payload):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        headers = {'HTTP_X_CSRFTOKEN': token.value} if token else {}
        return self.client.post(url, payload, format='json', **headers)

    def test_requires_maintenance_permission(self):
        self.client.force_login(User.objects.create_user(username='reader', password='pw'))
        self.assertEqual(self.client.get('/api/admin/ai-notice/').status_code, 403)

    def test_list_and_exempt(self):
        self.client.force_login(User.objects.create_superuser(username='admin', password='pw'))
        data = self.client.get('/api/admin/ai-notice/').json()
        self.assertTrue(data['config']['enabled'])
        self.assertEqual(data['counts']['active'], 1)
        self.assertEqual(data['results'][0]['status'], 'active')

        response = self._post(f'/api/admin/ai-notice/{self.datafile.pk}/exempt/', {'exempt': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'exempt')
        self.assertFalse(has_notice(Path(self.datafile.datafile)))

        response = self._post(f'/api/admin/ai-notice/{self.datafile.pk}/exempt/', {'exempt': False})
        self.assertEqual(response.json()['status'], 'active')
        self.assertTrue(has_notice(Path(self.datafile.datafile)))
