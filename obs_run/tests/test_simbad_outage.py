"""SIMBAD outages: timeout, pause after connection failures, no negative caching, later resolution."""
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

import utilities
from objects.models import Object
from obs_run.models import DataFile, ObservationRun


def _simbad(query_object=None, query_region=None):
    instance = MagicMock()
    if query_object is not None:
        instance.query_object.side_effect = query_object
    if query_region is not None:
        instance.query_region.side_effect = query_region
    return MagicMock(return_value=instance)


class SimbadOutageTest(TestCase):
    def setUp(self):
        utilities._SIMBAD_DOWN_UNTIL = 0.0
        utilities._SIMBAD_NEGATIVE_CACHE.clear()
        patcher = patch.object(utilities, '_simbad_rate_limit')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, utilities, '_SIMBAD_DOWN_UNTIL', 0.0)

    def test_connection_error_pauses_queries_without_negative_caching(self):
        simbad_cls = _simbad(query_object=requests.exceptions.ConnectionError('Connection refused'))
        with patch.object(utilities, 'Simbad', simbad_cls):
            self.assertIsNone(utilities._query_object_variants('M42'))
            self.assertFalse(utilities._in_neg_cache('M42'))
            self.assertFalse(utilities.simbad_available())
            missed = utilities.simbad_missed_count()
            # While paused, no new SIMBAD request is made
            self.assertIsNone(utilities._query_object_variants('M 31'))
            self.assertIsNone(utilities._query_region_safe(10.0, 41.0))
        self.assertEqual(simbad_cls.call_count, 1)
        self.assertEqual(utilities.simbad_missed_count(), missed + 2)

    def test_unknown_name_is_still_cached(self):
        with patch.object(utilities, 'Simbad', _simbad(query_object=lambda name: None)):
            self.assertIsNone(utilities._query_object_variants('Not a real object'))
        self.assertTrue(utilities._in_neg_cache('Not a real object'))
        self.assertTrue(utilities.simbad_available())

    def test_unreachable_tap_service_counts_as_outage(self):
        # pyvo's message when CDS is down (seen in production)
        error = Exception('DALServiceError: Unable to access the capabilities endpoint')
        with patch.object(utilities, 'Simbad', _simbad(query_region=error)):
            self.assertIsNone(utilities._query_region_safe(10.0, 41.0))
        self.assertFalse(utilities.simbad_available())

    def test_requests_get_a_default_timeout(self):
        adapter = utilities._TimeoutAdapter((3, 7))
        with patch.object(requests.adapters.HTTPAdapter, 'send', return_value='ok') as send:
            adapter.send(MagicMock())
            self.assertEqual(send.call_args.kwargs['timeout'], (3, 7))
            adapter.send(MagicMock(), timeout=99)
            self.assertEqual(send.call_args.kwargs['timeout'], 99)


class SimbadRetryTest(TestCase):
    def setUp(self):
        utilities._SIMBAD_DOWN_UNTIL = 0.0
        self.addCleanup(setattr, utilities, '_SIMBAD_DOWN_UNTIL', 0.0)
        self.run = ObservationRun.objects.create(name='2026-10-29', is_public=True)
        self.datafile = DataFile.objects.create(observation_run=self.run, datafile='/tmp/m42.fits', file_type='FITS')

    def _evaluate(self, simbad_failed):
        obj = Object.objects.create(name='M42_field', is_public=True, object_type='UK', ra=83.8, dec=-5.4)

        def fake_evaluation(*args, **kwargs):
            if simbad_failed:
                utilities._simbad_missed()
            return {'status': 'new_object_created', 'new_object': obj}

        with patch.object(utilities, '_evaluate_data_file', side_effect=fake_evaluation):
            utilities.evaluate_data_file(self.datafile, self.run)
        obj.refresh_from_db()
        return obj

    def test_object_created_during_outage_is_flagged(self):
        self.assertTrue(self._evaluate(simbad_failed=True).simbad_retry)
        self.assertFalse(self._evaluate(simbad_failed=False).simbad_retry)

    def test_retry_resolves_by_name_once_simbad_is_back(self):
        obj = self._evaluate(simbad_failed=True)
        row = {'main_id': 'M  42'}
        with patch.object(utilities, '_query_object_variants', return_value=[row]), \
                patch.object(utilities, 'update_object_from_simbad_result') as update:
            summary = utilities.retry_simbad_objects()
        self.assertEqual(summary['resolved'], 1)
        update.assert_called_once()
        self.assertIs(update.call_args.args[1], row)
        self.assertFalse(update.call_args.kwargs['bypass_override_flags'])
        obj.refresh_from_db()
        self.assertFalse(obj.simbad_retry)

    def test_retry_keeps_flag_while_simbad_is_down(self):
        obj = self._evaluate(simbad_failed=True)
        utilities._SIMBAD_DOWN_UNTIL = utilities.time.monotonic() + 600
        summary = utilities.retry_simbad_objects()
        self.assertEqual((summary['resolved'], summary['simbad_available']), (0, False))
        obj.refresh_from_db()
        self.assertTrue(obj.simbad_retry)
