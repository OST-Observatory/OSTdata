"""Classifier integration: archive metadata for v2 models, top class when abstaining, storing the result."""
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from obs_run.ml_classification import ExposureTypeClassifier, apply_ml_result
from obs_run.models import DataFile, ObservationRun


class _LegacyRunner:
    """predict_paths without metadata (pinned legacy ost_image_classification)."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def predict_paths(self, paths, batch_size=32):
        self.calls.append((paths, None))
        return {'results': [{'path': paths[0], **self.result}]}


class _V2Runner(_LegacyRunner):
    def predict_paths(self, paths, batch_size=32, metadata=None):
        self.calls.append((paths, metadata))
        return {'results': [{'path': paths[0], **self.result}]}


@override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=[r'qhy\s*600m'])
class ClassifyDatafileTest(TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / 'f.fits').write_bytes(b'SIMPLE')
        run = ObservationRun.objects.create(name='spec-night', spectroscopy=True)
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(tmp / 'f.fits'), file_type='FITS', instrument='QHY268M',
            exposure_type='LI', plate_solved=False,
        )
        self.service = ExposureTypeClassifier()
        self.addCleanup(self._reset)

    def _reset(self):
        self.service._classifier = None
        self.service._accepts_metadata = None

    def _classify(self, runner):
        self._reset()
        self.service._classifier = runner
        return self.service.classify_datafile(self.datafile)

    def test_v2_runner_gets_metadata_and_top_class(self):
        runner = _V2Runner({'class': 'unknown', 'score': 0.41, 'abstained': True, 'top_class': 'spectrum_dados'})
        result = self._classify(runner)
        self.assertEqual(runner.calls[0][1], {self.datafile.datafile: {
            'instrument': 'QHY 268M', 'plate_solved': False, 'run_spectroscopy': True,
        }})
        self.assertEqual((result['exposure_type_ml'], result['ml_top_class']), ('UK', 'spectrum_dados'))

    def test_legacy_runner_without_metadata(self):
        runner = _LegacyRunner({'class': 'spectrum_baches', 'score': 0.9, 'abstained': False})
        result = self._classify(runner)
        self.assertIsNone(runner.calls[0][1])
        self.assertEqual((result['exposure_type_ml'], result['spectrograph_ml'], result['ml_top_class']),
                         ('LI', 'B', 'spectrum_baches'))

    def test_missing_file_result_is_complete(self):
        self.datafile.datafile = '/nonexistent/x.fits'
        result = self._classify(_V2Runner({}))
        self.assertIn('spectrograph_ml', result)
        self.assertTrue(result['error'])

    def test_apply_ml_result(self):
        result = {'exposure_type_ml': 'DA', 'exposure_type_ml_confidence': 0.8, 'exposure_type_ml_abstained': False,
                  'spectrograph_ml': 'B', 'ml_top_class': 'darks'}
        self.datafile.save(update_fields=apply_ml_result(self.datafile, result))
        self.datafile.refresh_from_db()
        # the raw suggestion is kept, the stored spectrograph follows the rules (header LI vs. classifier DA -> UK)
        self.assertEqual((self.datafile.spectrograph_ml, self.datafile.ml_top_class), ('B', 'darks'))
        self.assertEqual(self.datafile.exposure_type_ml, 'DA')
