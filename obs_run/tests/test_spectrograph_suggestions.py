"""Spectrograph suggestions (heuristics + evaluation), classification filters and the bulk admin endpoint."""
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from obs_run.models import DataFile, HeuristicReport, ObservationRun, SpectrographSuggestion
from obs_run.spectrograph_heuristics import analyse, apply_agreed_suggestions, recompute_suggestions
from obs_run.tests.test_visibility_acl import _grant
from ostdata.history_reason import REASON_ADMIN_SPECTROGRAPH, save_with_reason

User = get_user_model()

SMALL_PARAMS = {'token_min_support': 5, 'token_min_runs': 2, 'token_max_run_share': 1.0}


def _file(run, spectrograph, exposure_type='LI', directory='spectra', name=None, **kwargs):
    count = DataFile.objects.count()
    return DataFile.objects.create(
        observation_run=run, datafile=f'/archive/{run.name}/{directory}/{name or f"f{count}"}.fit',
        file_type='FITS', exposure_type=exposure_type, exposure_type_ml=exposure_type,
        spectrograph=spectrograph, **kwargs,
    )


def _review(datafile, spectrograph):
    datafile.spectrograph = spectrograph
    datafile.spectrograph_override = True
    save_with_reason(datafile, REASON_ADMIN_SPECTROGRAPH, update_fields=['spectrograph', 'spectrograph_override'])


class SpectrographHeuristicsTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='dados-night')
        for _ in range(15):  # 15 of 18 files D before the review (> 80 %)
            _file(self.run, 'D')
        self.outlier = _file(self.run, 'N')  # unreviewed: run majority suggests D
        self.corrected = _file(self.run, 'N')
        _review(self.corrected, 'D')  # reviewed correction the run majority would have found
        self.confirmed = _file(self.run, 'N')
        _review(self.confirmed, 'N')  # reviewed confirmation: run majority suggestion would have been wrong
        _file(self.run, 'B', exposure_type='DA')  # darks are not considered

        other = ObservationRun.objects.create(name='imaging-night')
        for _ in range(3):
            _file(other, 'N', directory='lights')
        self.missed = _file(other, 'N', directory='lights')
        _review(self.missed, 'B')  # correction no heuristic finds

    def test_suggestions(self):
        result = analyse()
        self.assertEqual(result['suggestions'], {self.outlier.pk: ('D', None)})

    def test_evaluation(self):
        evaluation = analyse()['report']['evaluation']['run_majority']
        self.assertEqual((evaluation['tp'], evaluation['fp'], evaluation['fn']), (1, 1, 1))
        self.assertEqual(evaluation['precision'], 0.5)
        self.assertEqual(evaluation['recall'], 0.5)
        self.assertEqual(evaluation['transitions'], {'N -> D': {'tp': 1, 'fp': 1}})

    def test_path_tokens(self):
        for i in range(2):
            run = ObservationRun.objects.create(name=f'baches-{i}')
            for _ in range(10):
                _file(run, 'B', directory='baches')
        stray = _file(ObservationRun.objects.create(name='stray'), 'N', directory='baches')

        result = analyse(SMALL_PARAMS)

        self.assertEqual(result['suggestions'][stray.pk], (None, 'B'))
        self.assertIn('baches', result['report']['indicative_tokens'])

    def test_recompute_replaces_stored_suggestions(self):
        recompute_suggestions()
        self.assertEqual(
            list(SpectrographSuggestion.objects.values_list('datafile_id', 'run_majority', 'path_token')),
            [(self.outlier.pk, 'D', None)],
        )
        DataFile.objects.filter(pk=self.outlier.pk).update(spectrograph='D')
        recompute_suggestions()
        self.assertFalse(SpectrographSuggestion.objects.exists())
        report = HeuristicReport.objects.get(name='spectrograph_suggestions')
        self.assertEqual(report.data['reviewed_files'], 3)

    def test_command(self):
        out = StringIO()
        call_command('compute_spectrograph_suggestions', stdout=out)
        self.assertIn('1 suggestions stored', out.getvalue())


class AdminClassificationApiTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='mixed', is_public=True)
        self.spectra = [_file(self.run, 'D') for _ in range(10)]  # 10 of 12 relevant files D
        self.outlier = _file(self.run, 'N')
        self.wave_without_spectrograph = _file(self.run, 'N', exposure_type='WA')
        self.disagreement = _file(self.run, 'N', exposure_type='LI')
        DataFile.objects.filter(pk=self.disagreement.pk).update(exposure_type_ml='DA')
        recompute_suggestions()
        self.user = User.objects.create_user(username='curator', password='pw')
        self.client.force_login(self.user)
        self.client.get('/api/users/auth/csrf/')

    def _headers(self):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    def _list(self, **params):
        response = self.client.get('/api/admin/datafiles/', {'limit': 100, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return {row['pk'] for row in response.json()['results']}

    def _bulk(self, payload):
        return self.client.post('/api/admin/datafiles/classification/', payload, format='json', **self._headers())

    def test_filters(self):
        _grant(self.user, 'acl_datafiles_spectrograph')
        # The run majority also resolves the WAVE frame without spectrograph
        suggested = {self.outlier.pk, self.wave_without_spectrograph.pk}
        self.assertEqual(self._list(has_spectrograph_suggestion='any'), suggested)
        self.assertEqual(self._list(has_spectrograph_suggestion='token'), set())
        self.assertEqual(self._list(invalid_combination='true'), {self.wave_without_spectrograph.pk})
        self.assertEqual(self._list(exposure_disagreement='true'), {self.disagreement.pk})
        self.assertEqual(len(self._list(spectrograph=['N', 'D'])), 13)

    def test_suggestion_serialized(self):
        _grant(self.user, 'acl_datafiles_spectrograph')
        response = self.client.get('/api/admin/datafiles/', {'has_spectrograph_suggestion': 'any'})
        suggestion = response.json()['results'][0]['spectrograph_suggestion']
        self.assertEqual((suggestion['run_majority'], suggestion['path_token']), ('D', None))

    def test_accept_suggestion_closes_it(self):
        _grant(self.user, 'acl_datafiles_spectrograph')
        response = self._bulk({'ids': [self.outlier.pk], 'spectrograph': 'D', 'spectrograph_override': True})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['updated'], 1)
        self.assertEqual(self._list(has_spectrograph_suggestion='any'), {self.wave_without_spectrograph.pk})
        self.outlier.refresh_from_db()
        self.assertEqual((self.outlier.spectrograph, self.outlier.spectrograph_override), ('D', True))

    def test_permissions_per_field(self):
        _grant(self.user, 'acl_datafiles_exposure_type_user')
        response = self._bulk({'ids': [self.outlier.pk], 'spectrograph': 'D'})
        self.assertEqual(response.status_code, 403)
        response = self._bulk({'ids': [self.outlier.pk], 'exposure_type_user': 'XX'})
        self.assertEqual(response.status_code, 400)

    def test_combined_update_and_run_flags(self):
        _grant(self.user, 'acl_datafiles_exposure_type_user')
        _grant(self.user, 'acl_datafiles_spectrograph')
        ids = [f.pk for f in self.spectra]
        self.run.spectroscopy = True
        self.run.save()

        response = self._bulk({'ids': ids, 'exposure_type_user': 'DA', 'exposure_type_user_override': True})

        self.assertEqual(response.json()['updated'], 10)
        values = set(DataFile.objects.filter(pk__in=ids).values_list('exposure_type_user', 'spectrograph'))
        self.assertEqual(values, {('DA', 'N')})  # darks carry no spectrograph
        self.run.refresh_from_db()
        self.assertFalse(self.run.spectroscopy)

    def test_evaluation_and_recompute_endpoints(self):
        _grant(self.user, 'acl_datafiles_spectrograph')
        response = self.client.get('/api/admin/spectrograph-suggestions/evaluation/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['open_now'], {'run_majority': 2, 'path_token': 0, 'both': 0})
        with mock.patch('adminops.api.views._celery_delay', return_value=mock.Mock(id='task-1')) as delay:
            response = self.client.post('/api/admin/spectrograph-suggestions/recompute/', **self._headers())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['task_id'], 'task-1')
        delay.assert_called_once()

    def test_suggestion_endpoints_need_permission(self):
        response = self.client.get('/api/admin/spectrograph-suggestions/evaluation/')
        self.assertEqual(response.status_code, 403)


class DataFileWritePermissionTest(APITestCase):
    def setUp(self):
        run = ObservationRun.objects.create(name='public', is_public=True)
        self.datafile = _file(run, 'N')
        self.url = f'/api/runs/datafiles/{self.datafile.pk}/'
        self.client.get('/api/users/auth/csrf/')

    def _headers(self):
        token = self.client.cookies.get(settings.CSRF_COOKIE_NAME)
        return {'HTTP_X_CSRFTOKEN': token.value} if token else {}

    def test_plain_user_cannot_modify_or_delete(self):
        self.client.force_login(User.objects.create_user(username='reader', password='pw'))
        response = self.client.patch(self.url, {'instrument': 'hacked'}, format='json', **self._headers())
        self.assertEqual(response.status_code, 403)
        response = self.client.delete(self.url, **self._headers())
        self.assertEqual(response.status_code, 403)
        self.assertTrue(DataFile.objects.filter(pk=self.datafile.pk, instrument='').exists())

    def test_superuser_can_modify(self):
        self.client.force_login(User.objects.create_superuser(username='admin', password='pw'))
        response = self.client.patch(self.url, {'instrument': 'QHY268M'}, format='json', **self._headers())
        self.assertEqual(response.status_code, 200, response.content)


class LeaveOneRunOutTest(TestCase):
    def test_reviewed_run_does_not_confirm_its_own_token(self):
        reviewed_run = ObservationRun.objects.create(name='night-a')
        for _ in range(10):
            _review(_file(reviewed_run, 'N', directory='solo'), 'B')
        other_run = ObservationRun.objects.create(name='night-b')
        for _ in range(10):
            _file(other_run, 'B', directory='solo')

        evaluation = analyse(SMALL_PARAMS)['report']['evaluation']

        # In-sample the reviewed run supports the token itself; leave-one-run-out only one run is left
        self.assertEqual(evaluation['path_token_in_sample']['tp'], 10)
        self.assertEqual((evaluation['path_token']['tp'], evaluation['path_token']['fn']), (0, 10))


@override_settings(SPECTROGRAPH_IMAGING_ONLY_INSTRUMENTS=[r'qhy\s*600m'])
class AutoApplyTest(TestCase):
    def setUp(self):
        runs = [ObservationRun.objects.create(name=f'dados-{i}') for i in range(3)]
        for run in runs:
            for _ in range(20):  # token purity 60 / 63 > 95 %
                _file(run, 'D', directory='dados')
        self.outlier = _file(runs[0], 'N', directory='dados')  # run majority and path token: DADOS
        self.imaging = _file(runs[1], 'N', directory='dados', instrument='QHY 600M')  # rules forbid DADOS
        self.manual = _file(runs[2], 'N', directory='dados')
        _review(self.manual, 'N')

    def _spectrograph(self, datafile):
        return DataFile.objects.get(pk=datafile.pk).spectrograph

    def test_dry_run(self):
        recompute_suggestions(SMALL_PARAMS, auto_apply=False)
        changes = apply_agreed_suggestions(dry_run=True)
        self.assertEqual([(pk, old, new) for pk, old, new, _ in changes], [(self.outlier.pk, 'N', 'D')])
        self.assertEqual(self._spectrograph(self.outlier), 'N')

    def test_agreeing_suggestion_applied_without_override(self):
        result = recompute_suggestions(SMALL_PARAMS, auto_apply=True)

        self.assertEqual(result['report']['auto_applied']['count'], 1)
        outlier = DataFile.objects.get(pk=self.outlier.pk)
        self.assertEqual((outlier.spectrograph, outlier.spectrograph_override), ('D', False))
        self.assertEqual(outlier.history.latest().history_change_reason, 'task:spectrograph_suggestion')
        self.assertEqual(self._spectrograph(self.imaging), 'N')
        self.assertEqual(self._spectrograph(self.manual), 'N')

    def test_correcting_an_applied_value_counts_against_the_heuristic(self):
        recompute_suggestions(SMALL_PARAMS, auto_apply=True)
        _review(DataFile.objects.get(pk=self.outlier.pk), 'B')

        evaluation = analyse(SMALL_PARAMS)['report']['evaluation']

        # State before the review is the classifier value N, not the applied D: the correction to B counts as a
        # wrong suggestion N -> D (the second one is the confirmed 'manual' file)
        self.assertEqual(evaluation['both']['transitions'].get('N -> D'), {'fp': 2})
        self.assertEqual(evaluation['both']['tp'], 0)
