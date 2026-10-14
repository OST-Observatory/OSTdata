"""Spectrograph suggestions (heuristics + evaluation), classification filters and the bulk admin endpoint."""
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run.models import DataFile, HeuristicReport, ObservationRun, SpectrographSuggestion
from obs_run.spectrograph_heuristics import analyse, recompute_suggestions
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
        self.assertEqual(response.json()['open_now'], {'run_majority': 2, 'path_token': 0})
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
