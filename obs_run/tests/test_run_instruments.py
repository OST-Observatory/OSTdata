"""Run summary: instruments (photometry cameras, spectrographs) and calibration-only runs."""
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


class CalibrationOnlyRunTest(APITestCase):
    def _run(self, name, exposure_types):
        run = ObservationRun.objects.create(name=name, is_public=True)
        for idx, exposure_type in enumerate(exposure_types):
            DataFile.objects.create(
                observation_run=run, datafile=f'/tmp/{name}-{idx}.fits', file_type='FITS',
                exposure_type=exposure_type, exposure_type_ml=exposure_type,
            )
        return run

    def test_calibration_only_flag(self):
        cases = {
            self._run('cal', ['BI', 'DA', 'FL', 'WA']).pk: True,
            self._run('science', ['DA', 'LI']).pk: False,
            self._run('unclear', ['DA', 'UK']).pk: False,  # unknown frames: not certain
            self._run('empty', []).pk: False,
        }
        rows = {row['pk']: row for row in self.client.get('/api/runs/runs/').json()['results']}
        for pk, expected in cases.items():
            with self.subTest(run=rows[pk]['name']):
                self.assertIs(rows[pk]['calibration_only'], expected)
                detail = self.client.get(f'/api/runs/runs/{pk}/').json()
                self.assertIs(detail['calibration_only'], expected)


class RunExposureCountsTest(APITestCase):
    def test_disagreeing_frames_are_not_counted_by_header_type(self):
        # Header says flat, classifier says light: effective type unknown (column 'Other')
        run = ObservationRun.objects.create(name='2022-12-26', is_public=True)
        for idx in range(3):
            DataFile.objects.create(
                observation_run=run, datafile=f'/tmp/fl{idx}.fits', file_type='FITS',
                exposure_type='FL', exposure_type_ml='LI',
            )
        DataFile.objects.create(
            observation_run=run, datafile='/tmp/da.fits', file_type='FITS', exposure_type='DA', exposure_type_ml='DA',
        )
        row = self.client.get('/api/runs/runs/').json()['results'][0]
        self.assertEqual(
            (row['n_datafiles'], row['n_light'], row['n_flat'], row['n_dark']), (4, 0, 0, 1),
        )
        detail = self.client.get(f'/api/runs/runs/{run.pk}/').json()
        self.assertEqual((detail['n_flat'], detail['n_dark']), (0, 1))
