"""classify_exposure_types --compare / --sample / --run: compare a classifier with the stored values, save nothing."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from obs_run.ml_classification import ExposureTypeClassifier
from obs_run.models import DataFile, ObservationRun


class _Runner:
    """ClassifierService stand-in: predicted class per file name."""

    def __init__(self, classes):
        self.classes = classes

    def predict_paths(self, paths, batch_size=32, metadata=None):
        name = Path(paths[0]).name
        return {'results': [{'path': paths[0], 'class': self.classes[name], 'score': 0.9, 'abstained': False,
                             'top_class': self.classes[name]}]}


@override_settings(ML_EXPOSURE_TYPE_ENABLED=True, EXPOSURE_TYPE_EFFECTIVE_RULE='header_first',
                   SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=[])
class CompareTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        run = ObservationRun.objects.create(name='2024-12-12', spectroscopy=True)
        other = ObservationRun.objects.create(name='2018-07-06', spectroscopy=False)
        # unlabelled: header LI, old ML DA -> UK; new ML LI -> LI
        self.unlabelled = self._file(run, 'light.fit', exposure_type='LI', exposure_type_ml='DA',
                                     exposure_type_ml_confidence=0.8)
        # manual WA and manual spectrograph D; old ML DA (wrong), new ML WA (correct)
        self.labelled = self._file(run, 'arc.fit', exposure_type='LI', exposure_type_ml='DA',
                                   exposure_type_ml_confidence=0.8, exposure_type_user='WA',
                                   spectrograph='D', spectrograph_override=True)
        self.other_run = self._file(other, 'moon.fit', exposure_type='LI')
        self.service = ExposureTypeClassifier()
        self.service._classifier = _Runner({'light.fit': 'deep_sky', 'arc.fit': 'wavelength_calibration_dados',
                                            'moon.fit': 'darks'})
        self.service._accepts_metadata = None
        self.addCleanup(setattr, self.service, '_classifier', None)

    def _file(self, run, name, **fields):
        path = self.tmp / name
        path.write_bytes(b'SIMPLE')
        return DataFile.objects.create(observation_run=run, datafile=str(path), file_type='FITS', **fields)

    def _compare(self, **options):
        out = self.tmp / 'compare.json'
        call_command('classify_exposure_types', compare=True, json=str(out), stdout=StringIO(), **options)
        return json.loads(out.read_text())

    def test_compare_reports_changes_and_saves_nothing(self):
        data = self._compare(run='2024-12-12')
        summary = data['summary']
        self.assertEqual(summary['files'], 2)
        self.assertEqual({c['change']: c['n'] for c in summary['ml_changes']}, {'DA -> LI': 1, 'DA -> WA': 1})
        unlabelled = summary['without_manual_label']
        self.assertEqual((unlabelled['n'], unlabelled['uk_before'], unlabelled['uk_after']), (1, 1, 0))
        self.assertEqual(unlabelled['changes'][0]['change'], 'UK -> LI')
        manual = summary['with_manual_label']
        self.assertEqual((manual['old']['wrong'], manual['new']['correct']), (1.0, 1.0))
        self.assertEqual(summary['spectrograph']['manual']['new_correct'], 1.0)

        for datafile in (self.unlabelled, self.labelled):
            before = (datafile.exposure_type_ml, datafile.spectrograph)
            datafile.refresh_from_db()
            self.assertEqual((datafile.exposure_type_ml, datafile.spectrograph), before)

    def test_compare_lists_wrong_new_suggestions(self):
        self.service._classifier.classes['arc.fit'] = 'darks'
        manual = self._compare(run=str(self.labelled.observation_run_id))['summary']['with_manual_label']
        self.assertEqual(manual['new']['wrong'], 1.0)
        self.assertEqual(manual['new_errors'][0]['change'], 'WA -> DA')

    def test_sample_is_random_but_reproducible(self):
        first = [f['id'] for f in self._compare(sample=2, seed=3)['files']]
        again = [f['id'] for f in self._compare(sample=2, seed=3)['files']]
        self.assertEqual(len(first), 2)
        self.assertEqual(first, again)

    def test_files_never_classified(self):
        data = self._compare(run='2018-07-06')
        self.assertEqual(data['summary']['ml_changes'][0]['change'], '- -> DA')
