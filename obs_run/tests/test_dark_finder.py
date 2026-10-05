"""Dark finder API: dark (default) and bias search."""
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DataFile, ObservationRun

User = get_user_model()

URL = '/api/runs/dark-finder/'
SETUP = {'instrument': 'QHY 600M', 'ccd_temp': -20.0, 'naxis1': 4788, 'naxis2': 3194,
         'binning_x': 2, 'binning_y': 2}


class DarkFinderTest(APITestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='2026-03-17', is_public=True)
        self.dark = self._file(run, 'dark_120s.fit', 'DA', 120.0, 2461117.5)
        self.bias = self._file(run, 'bias.fit', 'BI', 0.0, 2461117.6)
        self._file(run, 'light_120s.fit', 'LI', 120.0, 2461117.7)
        self.user = User.objects.create_user(username='reader', password='reader-pass')
        self.client.get('/api/users/auth/csrf/')
        self.client.force_login(self.user)

    @staticmethod
    def _file(run, name, etype, exptime, hjd):
        return DataFile.objects.create(
            observation_run=run, datafile=f'/tmp/{name}', file_type='FITS', file_size=8,
            exposure_type=etype, exposure_type_ml=etype, exptime=exptime, hjd=hjd,
            ccd_temp=-19.9,
            instrument=SETUP['instrument'], naxis1=SETUP['naxis1'], naxis2=SETUP['naxis2'],
            binning_x=2, binning_y=2,
        )

    def _post(self, payload):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        headers = {'HTTP_X_CSRFTOKEN': token.value} if token else {}
        return self.client.post(URL, payload, format='json', **headers)

    def test_dark_search_is_the_default(self):
        resp = self._post({**SETUP, 'exptime': 123.0, 'exptime_tolerance': 5})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([r['id'] for r in resp.data['results']], [self.dark.pk])
        self.assertEqual(resp.data['frame_type'], 'dark')

    def test_bias_search_ignores_the_exposure_time(self):
        resp = self._post({**SETUP, 'frame_type': 'bias'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([r['id'] for r in resp.data['results']], [self.bias.pk])
        self.assertEqual(resp.data['results'][0]['frame_type'], 'bias')

    def test_invalid_requests(self):
        self.assertEqual(self._post({**SETUP, 'frame_type': 'flat'}).status_code,
                         status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._post(dict(SETUP)).status_code, status.HTTP_400_BAD_REQUEST)
