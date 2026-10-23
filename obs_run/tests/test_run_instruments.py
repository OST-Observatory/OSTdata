"""Instruments per observation run: photometry cameras and spectrographs of the light frames."""
from rest_framework.test import APITestCase

from obs_run.api.serializers import runs_instruments
from obs_run.models import DataFile, ObservationRun


class RunInstrumentsTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-10-05', is_public=True, photometry=True, spectroscopy=True)
        self.empty_run = ObservationRun.objects.create(name='2026-10-06', is_public=True)
        files = [
            ('LI', 'N', 'QHY600M'),        # photometry, raw header name -> 'QHY 600M'
            ('LI', 'N', 'QHY600M'),        # duplicate camera
            ('LI', 'N', 'SBIG ST-8'),
            ('LI', 'N', 'UK'),             # unknown camera: not listed
            ('LI', 'D', 'QHY268M'),        # spectrum: spectrograph, not camera
            ('DA', 'N', 'ZWO ASI174MM'),   # calibration frame: ignored
        ]
        for idx, (exposure_type, spectrograph, instrument) in enumerate(files):
            DataFile.objects.create(
                observation_run=self.run, datafile=f'/tmp/{idx}.fits', file_type='FITS',
                exposure_type=exposure_type, spectrograph=spectrograph, instrument=instrument,
            )

    def test_runs_instruments(self):
        result = runs_instruments([self.run.pk, self.empty_run.pk])
        self.assertEqual(result[self.run.pk], {'photometry': ['QHY 600M', 'SBIG ST-8'], 'spectroscopy': ['D']})
        self.assertEqual(result[self.empty_run.pk], {'photometry': [], 'spectroscopy': []})

    def test_list_and_detail_include_instruments(self):
        rows = {row['pk']: row for row in self.client.get('/api/runs/runs/').json()['results']}
        self.assertEqual(rows[self.run.pk]['instruments']['photometry'], ['QHY 600M', 'SBIG ST-8'])
        self.assertEqual(rows[self.empty_run.pk]['instruments'], {'photometry': [], 'spectroscopy': []})

        detail = self.client.get(f'/api/runs/runs/{self.run.pk}/').json()
        self.assertEqual(detail['instruments']['spectroscopy'], ['D'])
