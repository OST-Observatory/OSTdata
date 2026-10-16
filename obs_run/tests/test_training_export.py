"""Training data export v2: labels, hard cases, per-class caps and run-based splits."""
import json
import random
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from obs_run.management.commands.export_cnn_training_data import Command as ExportCommand
from obs_run.models import DataFile, ObservationRun
from obs_run.training_export import cap_per_class, collect_records, label, split_by_run
from ostdata.history_reason import REASON_ADMIN_SPECTROGRAPH, save_with_reason

ARCHIVE = Path('/archive/data')


def _row(header='LI', ml='LI', user=None, spectrograph='N', override=False):
    return {
        'exposure_type': header, 'exposure_type_ml': ml, 'exposure_type_user': user,
        'spectrograph': spectrograph, 'spectrograph_override': override,
    }


class LabelTest(TestCase):
    def test_label_sources(self):
        cases = [
            (_row(user='DA'), ('darks', 'manual')),
            (_row(header='FL', ml='FL', spectrograph='B'), ('flat_baches', 'agreement')),
            (_row(header='LI', ml='DA'), None),  # disagreement without manual label
            (_row(header='UK', ml='UK'), None),
            (_row(header='WA', ml='WA', spectrograph='N'), None),  # invalid combination
            (_row(spectrograph='D', override=True), ('spectrum_dados', 'manual')),
            (_row(user='UK'), None),
        ]
        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(label(row), expected)


class CollectRecordsTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='night', spectroscopy=True)

    def _file(self, name, **kwargs):
        defaults = {'exposure_type': 'LI', 'exposure_type_ml': 'LI', 'exposure_type_ml_confidence': 0.9}
        return DataFile.objects.create(
            observation_run=self.run, datafile=str(ARCHIVE / 'night' / name), file_type='FITS',
            obs_date='2024-05-01T22:00:00', instrument='QHY600M', **{**defaults, **kwargs},
        )

    def _records(self):
        return {Path(r['path']).name: r for r in collect_records(['FITS'], ARCHIVE)}

    def test_records_and_hard_cases(self):
        self._file('agree.fit')
        self._file('fixed.fit', exposure_type='LI', exposure_type_ml='LI', exposure_type_user='DA')
        self._file('confirmed.fit', exposure_type_user='LI')
        DataFile.objects.create(
            observation_run=self.run, datafile='/elsewhere/x.fit', file_type='FITS',
            exposure_type='LI', exposure_type_ml='LI',
        )

        records = self._records()

        self.assertEqual(set(records), {'agree.fit', 'fixed.fit', 'confirmed.fit'})
        self.assertEqual(records['agree.fit']['label_source'], 'agreement')
        self.assertFalse(records['agree.fit']['hard'])
        self.assertTrue(records['fixed.fit']['hard'])
        self.assertEqual(records['fixed.fit']['class'], 'darks')
        self.assertFalse(records['confirmed.fit']['hard'])
        self.assertEqual(records['agree.fit']['instrument'], 'QHY 600M')
        self.assertEqual((records['agree.fit']['year'], records['agree.fit']['run_spectroscopy']), (2024, True))
        self.assertEqual(records['agree.fit']['path'], 'night/agree.fit')

    def test_spectrograph_correction_is_hard(self):
        corrected = self._file('spec.fit')
        corrected.spectrograph, corrected.spectrograph_override = 'D', True
        save_with_reason(corrected, REASON_ADMIN_SPECTROGRAPH, update_fields=['spectrograph', 'spectrograph_override'])
        kept = self._file('kept.fit')
        kept.spectrograph_override = True
        save_with_reason(kept, REASON_ADMIN_SPECTROGRAPH, update_fields=['spectrograph_override'])

        records = self._records()

        self.assertEqual(records['spec.fit']['class'], 'spectrum_dados')
        self.assertTrue(records['spec.fit']['hard'])
        self.assertFalse(records['kept.fit']['hard'])


def _record(pk, cls, run, hard=False):
    return {'pk': pk, 'class': cls, 'run': run, 'hard': hard}


class CapAndSplitTest(TestCase):
    def test_cap_keeps_hard_files_and_spreads_over_runs(self):
        records = [_record(i, 'darks', run=i % 4) for i in range(40)] + [_record(100, 'darks', run=9, hard=True)]
        kept = cap_per_class(records, 9, random.Random(1))
        self.assertEqual(len(kept), 9)
        self.assertIn(100, {r['pk'] for r in kept})
        self.assertEqual({r['run'] for r in kept if not r['hard']}, {0, 1, 2, 3})

    def test_split_by_run(self):
        records = [_record(i, 'deep_sky', run=i // 10) for i in range(400)]  # 40 runs
        records += [_record(1000 + i, 'einsteinturm', run=100 + i) for i in range(3)]  # rare: 3 runs
        split_by_run(records, (0.7, 0.15, 0.15), random.Random(1))

        run_splits = {}
        for r in records:
            run_splits.setdefault(r['run'], set()).add(r['split'])
        self.assertTrue(all(len(splits) == 1 for splits in run_splits.values()))
        self.assertEqual({r['split'] for r in records if r['class'] == 'einsteinturm'}, {'train', 'val', 'test'})
        train_share = sum(r['split'] == 'train' for r in records if r['class'] == 'deep_sky') / 400
        self.assertAlmostEqual(train_share, 0.7, delta=0.05)


class ExportCommandTest(TestCase):
    def setUp(self):
        for i in range(6):
            run = ObservationRun.objects.create(name=f'run{i}')
            for j in range(3):
                DataFile.objects.create(
                    observation_run=run, datafile=str(ARCHIVE / f'run{i}' / f'{j}.fit'), file_type='FITS',
                    exposure_type='DA', exposure_type_ml='DA',
                )

    def _export(self, *args):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(ExportCommand, '_data_directory', return_value=ARCHIVE):
            path = Path(tmp) / 'export.json'
            call_command('export_cnn_training_data', '--output', str(path), '--seed', '1', *args, stdout=StringIO())
            return json.loads(path.read_text())

    def test_v2(self):
        export = self._export()
        self.assertEqual(export['format'], 'ost-classification-export/v2')
        self.assertEqual(len(export['files']), 18)
        self.assertEqual(sum(export['runs'].values()), 6)
        self.assertEqual(set(export['files'][0]), {
            'pk', 'path', 'class', 'label_source', 'hard', 'run', 'instrument', 'year', 'file_type', 'exptime',
            'plate_solved', 'run_spectroscopy', 'split',
        })

    def test_v1_still_available(self):
        DataFile.objects.update(obs_date='2024-01-01T00:00:00')
        export = self._export('--format', 'v1')
        self.assertEqual(set(export), {'train', 'val', 'test'})
        self.assertEqual(sum(len(paths) for split in export.values() for paths in split.values()), 18)
