"""apply_exposure_type_name_rule: evaluation against manual labels (--dry-run) and backfill."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from obs_run.models import DataFile, ObservationRun


class NameRuleCommandTest(TestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='2024-12-12')
        with self.settings(EXPOSURE_TYPE_NAME_RULE=False):  # existing files: rule not filled in yet
            self.arc = self._file(run, 'DADOS_Ar-Ne-0001_1s.fit', exposure_type='LI', exposure_type_ml='DA')
            self.labelled = self._file(run, 'thar_2s.FIT', exposure_type='LI', exposure_type_user='WA')
            self.wrong = self._file(run, 'arc_test.fit', exposure_type='UK', exposure_type_user='LI')
            self.light = self._file(run, 'm42.fit', exposure_type='LI')
        self.out = Path(tempfile.mkdtemp()) / 'rule.json'

    def _file(self, run, name, **fields):
        return DataFile.objects.create(observation_run=run, datafile=f'/data/{name}', file_type='FITS', **fields)

    def test_dry_run_evaluates_and_changes_nothing(self):
        call_command('apply_exposure_type_name_rule', dry_run=True, json=str(self.out), stdout=StringIO())
        report = json.loads(self.out.read_text())
        self.assertEqual((report['matches'], report['with_manual_label'], report['manual_label_wa']), (3, 2, 1))
        self.assertEqual(report['purity'], 0.5)
        self.assertEqual(report['wrong_manual_labels'], {'LI': ['/data/arc_test.fit']})
        self.assertEqual(report['effective_changes_without_manual_label'][0]['change'], 'UK -> WA')
        self.assertEqual(set(report['tokens']), {'arne', 'thar', 'arc'})
        self.arc.refresh_from_db()
        self.assertEqual(self.arc.exposure_type_rule, '')

    def test_apply_needs_setting(self):
        with self.assertRaises(CommandError):
            call_command('apply_exposure_type_name_rule', stdout=StringIO())

    @override_settings(EXPOSURE_TYPE_NAME_RULE=True)
    def test_apply(self):
        call_command('apply_exposure_type_name_rule', stdout=StringIO())
        rules = dict(DataFile.objects.values_list('pk', 'exposure_type_rule'))
        self.assertEqual(rules, {self.arc.pk: 'WA', self.labelled.pk: 'WA', self.wrong.pk: 'WA', self.light.pk: ''})
        self.arc.refresh_from_db()
        self.wrong.refresh_from_db()
        self.assertEqual(self.arc.effective_exposure_type, 'WA')  # name rule over header LI / ML DA
        self.assertEqual(self.wrong.effective_exposure_type, 'LI')  # manual label wins
