"""exposure_type_report: cause classification of manual labels and the UK backlog."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings

from obs_run.models import DataFile, ObservationRun
from obs_run.spectrograph_heuristics import indicative_tokens
from ostdata.history_reason import REASON_ADMIN_SPECTROGRAPH, save_with_reason


class ExposureTypeReportTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-03-17')
        self.n = 0

    def _file(self, header, ml=None, confidence=0.95, abstained=False, user=None, path=None, run=None, **kwargs):
        self.n += 1
        return DataFile.objects.create(
            observation_run=run or self.run, datafile=path or f'/tmp/f{self.n}.fit', file_type='FITS',
            obs_date='2026-03-17T20:00:00', exposure_type=header,
            exposure_type_ml=ml, exposure_type_ml_confidence=confidence if ml else None,
            exposure_type_ml_abstained=abstained, exposure_type_user=user, **kwargs,
        )

    def _report(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            call_command('exposure_type_report', '--json', str(path), *args, stdout=StringIO())
            return json.loads(path.read_text())

    def test_manual_label_causes(self):
        self._file('UK', ml='LI', user='LI')
        self._file('UK', ml='UK', abstained=True, user='DA')
        self._file('DA', ml='UK', abstained=True, user='DA')
        self._file('DA', ml='LI', user='DA')
        self._file('LI', ml='FL', user='FL')
        self._file('LI', ml='LI', user='LI')
        self._file('UK', user='WA')

        causes = self._report()['manual_labels']['causes']

        self.assertEqual(causes, {
            'header_uk_ml_correct': 1,
            'header_uk_ml_abstained': 1,
            'header_correct_ml_abstained': 1,
            'header_correct_ml_wrong': 1,
            'header_wrong_ml_correct': 1,
            'confirmation': 1,
            'ml_not_run': 1,
        })

    def test_backlog_and_overrides(self):
        self._file('UK', ml='LI', confidence=0.995)
        self._file('UK', ml='UK', abstained=True)
        self._file('DA', ml='UK', abstained=True)
        self._file('DA', ml='LI')
        self._file('LI', ml='LI')  # agrees -> not in backlog
        self._file('FL', ml='FL', exposure_type_override=True)
        self._file('DA', ml='LI', exposure_type_override=True)

        report = self._report('--rule', 'agree')

        self.assertEqual(report['backlog_effective_uk']['categories'], {
            'header_uk_ml_confident': 1,
            'header_uk_ml_abstained': 1,
            'header_set_ml_abstained': 1,
            'header_ml_disagree': 1,
        })
        self.assertEqual(
            report['backlog_effective_uk']['ml_confidence']['header_uk_ml_confident'],
            {'0.99-1.00': 1},
        )
        self.assertEqual(report['backlog_effective_uk']['header_to_ml_disagreements'], {'DA -> LI': 1})
        self.assertEqual(report['header_field_overrides'], {'ml_correct': 1, 'ml_wrong': 1})
        self.assertEqual(report['totals']['header_field_overridden'], 2)

        report = self._report('--rule', 'header_first')

        self.assertEqual(report['backlog_effective_uk']['categories'], {
            'header_uk_ml_abstained': 1,
            'header_ml_disagree': 1,
        })

    def test_rule_simulation(self):
        self._file('UK', ml='LI', user='LI')  # header_first: correct, agree: review
        self._file('DA', ml='UK', abstained=True, user='DA')  # header_first: correct, agree: review
        self._file('DA', ml='LI', user='DA')  # both: review
        self._file('UK', ml='LI', user='DA')  # header_first: wrong, agree: review

        simulation = self._report()['manual_labels']['rule_simulation']

        self.assertEqual(simulation['header_first'], {'correct': 2, 'review': 1, 'wrong': 1})
        self.assertEqual(simulation['agree'], {'review': 4})

    def test_path_tokens(self):
        runs = [ObservationRun.objects.create(name=f'run-{i}') for i in range(3)]
        for run in runs:
            for _ in range(10):
                self._file('DA', ml='DA', run=run, path=f'/archive/{run.name}/darks/d{self.n}.fit')
                self._file('LI', ml='LI', run=run, path=f'/archive/{run.name}/lights/l{self.n}.fit')
        # Left at UK by the rule: one verifiable by its manual label, one not
        self._file('UK', ml='UK', abstained=True, user='DA', path='/archive/new/darks/x.fit')
        self._file('UK', ml='UK', abstained=True, path='/archive/new/lights/y.fit')

        tokens = self._report('--token-min-support', '10', '--token-max-run-share', '1')['path_tokens']

        self.assertEqual(tokens['indicative_tokens']['darks']['label'], 'DA')
        self.assertEqual(tokens['indicative_tokens']['lights']['label'], 'LI')
        self.assertNotIn('archive', tokens['indicative_tokens'])
        self.assertEqual(tokens['rule_uk_outcome'], {'correct': 1, 'unverified': 1})

    def test_format_filter(self):
        self._file('UK', ml='LI', user='LI')
        DataFile.objects.create(
            observation_run=self.run, datafile='/tmp/x.jpg', file_type='JPG',
            exposure_type='UK', exposure_type_user='LI',
        )

        report = self._report('--formats', 'jpg')

        self.assertEqual(report['totals']['files'], 1)
        self.assertEqual(report['manual_labels']['causes'], {'ml_not_run': 1})


class SpectrographReportTest(TestCase):
    def setUp(self):
        self.n = 0

    def _file(self, run, spectrograph, header='LI', ml='LI', directory='spectra', **kwargs):
        self.n += 1
        return DataFile.objects.create(
            observation_run=run, datafile=f'/archive/{run.name}/{directory}/f{self.n}.fit', file_type='FITS',
            exposure_type=header, exposure_type_ml=ml, exposure_type_ml_confidence=0.9,
            spectrograph=spectrograph, **kwargs,
        )

    @staticmethod
    def _correct(datafile, spectrograph):
        datafile.spectrograph = spectrograph
        datafile.spectrograph_override = True
        save_with_reason(datafile, REASON_ADMIN_SPECTROGRAPH, update_fields=['spectrograph', 'spectrograph_override'])

    def _report(self, *args):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.json'
            call_command('exposure_type_report', '--json', str(path), *args, stdout=StringIO())
            return json.loads(path.read_text())['spectrograph']

    def test_corrections_and_run_majority(self):
        run = ObservationRun.objects.create(name='dados-run')
        for _ in range(12):
            self._file(run, 'D')
        corrected = self._file(run, 'N')  # classifier missed the spectrograph, fixed manually
        self._correct(corrected, 'D')
        confirmed = self._file(run, 'D')
        self._correct(confirmed, 'D')
        self._file(run, 'N')  # uncorrected outlier
        self._file(run, 'N', header='WA', ml='WA')  # invalid combination

        report = self._report()

        self.assertEqual(report['corrections'], {'N -> D': 1, 'confirmed': 1})
        self.assertEqual(report['class_confusion'], {
            'deep_sky -> spectrum_dados': 1,
            'spectrum_dados -> spectrum_dados': 1,
        })
        self.assertEqual(report['correction_detection_run_majority'], {'flagged_correct': 1})
        self.assertEqual(report['suspicious_run_majority'], {'N (run majority D)': 2})
        self.assertEqual(report['invalid_combinations'], {'WA/N': {'automatic': 1}})

    @override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=[r'qhy\s*600m'])
    def test_rule_simulation(self):
        run = ObservationRun.objects.create(name='rules')
        dark = self._file(run, 'B', header='DA', ml='DA')
        self._correct(dark, 'N')  # fixed by the exposure type rule
        imaging = self._file(run, 'D', instrument='QHY 600M')
        self._correct(imaging, 'N')  # fixed by the instrument rule
        spectrum = self._file(run, 'N', instrument='QHY268M')
        self._correct(spectrum, 'D')  # rules cannot help
        self._file(run, 'E', header='BI', ml='BI')  # uncorrected, rule would change it

        report = self._report()

        self.assertEqual(report['rule_simulation_on_corrections'], {
            'fixed (exposure_type)': 1,
            'fixed (instrument)': 1,
            'unchanged': 1,
        })
        self.assertEqual(report['rule_changes_uncorrected'], {'E -> N (exposure_type)': 1})

    def test_path_tokens(self):
        for i in range(3):
            run = ObservationRun.objects.create(name=f'night-{i}')
            for _ in range(10):
                self._file(run, 'B', directory='baches')
                self._file(run, 'N', directory='lights')
        run = ObservationRun.objects.create(name='night-x')
        corrected = self._file(run, 'N', directory='baches')
        self._correct(corrected, 'B')
        self._file(run, 'N', directory='baches')  # uncorrected, contradicts the token

        report = self._report('--token-min-support', '10', '--token-max-run-share', '1')

        self.assertEqual(report['indicative_tokens']['baches']['label'], 'B')
        self.assertEqual(report['indicative_tokens']['lights']['label'], 'N')
        self.assertEqual(report['correction_prediction_tokens'], {'correct': 1})
        self.assertEqual(report['suspicious_tokens'], {'N (token says B)': 1})


class IndicativeTokensTest(TestCase):
    def test_generic_path_components_are_ignored(self):
        from collections import Counter
        token_labels = {
            'mnt': Counter({'N': 97, 'D': 3}),  # in every run, only mirrors the base rate
            'dados': Counter({'D': 30}),
        }
        token_runs = {'mnt': set(range(10)), 'dados': {1, 2, 3}}

        result = indicative_tokens(token_labels, token_runs, 10, 3, 0.95, 0.5)

        self.assertEqual(list(result), ['dados'])
