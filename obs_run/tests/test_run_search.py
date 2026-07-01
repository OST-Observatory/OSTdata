"""Tests for observation run auxiliary-object search."""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import ObservationRun
from obs_run.search import (
    build_run_aux_objects_search_q,
    find_aux_object_search_match,
)

User = get_user_model()


class RunAuxObjectSearchTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(
            name='2024-01-01_field',
            is_public=True,
            photometry=True,
            aux_objects_status=ObservationRun.AUX_STATUS_READY,
            aux_objects=[
                {
                    'name': 'M 31',
                    'ra': 10.68,
                    'dec': 41.27,
                    'object_type_display': 'Galaxy',
                },
                {
                    'name': 'HD 12345',
                    'ra': 10.7,
                    'dec': 41.3,
                    'object_type_display': 'Star',
                },
                {
                    'name': 'V* T Tau',
                    'ra': 10.71,
                    'dec': 41.31,
                    'object_type_display': 'Variable Star',
                },
            ],
        )
        self.empty_run = ObservationRun.objects.create(
            name='2024-01-02_empty',
            is_public=True,
            photometry=True,
            aux_objects_status=ObservationRun.AUX_STATUS_READY,
            aux_objects=[],
        )

    def test_find_aux_object_search_match_name(self):
        self.assertEqual(find_aux_object_search_match(self.run, 'M31'), 'M 31')
        self.assertEqual(find_aux_object_search_match(self.run, 'hd 123'), 'HD 12345')
        self.assertIsNone(find_aux_object_search_match(self.run, 'NGC 9999'))

    def test_build_run_aux_objects_search_q_finds_run(self):
        qs = ObservationRun.objects.filter(build_run_aux_objects_search_q('M31'))
        self.assertIn(self.run, qs)
        self.assertNotIn(self.empty_run, qs)

    def test_api_filter_aux_object(self):
        response = self.client.get('/api/runs/runs/', {'aux_object': 'M31'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pks = {item['pk'] for item in response.data['results']}
        self.assertIn(self.run.pk, pks)
        match = next(item for item in response.data['results'] if item['pk'] == self.run.pk)
        self.assertEqual(match['search_match_via_aux'], 'M 31')

    def test_api_filter_aux_object_no_match(self):
        response = self.client.get('/api/runs/runs/', {'aux_object': 'NGC 404'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'], [])

    def test_partial_aux_object_name_suffix(self):
        self.assertEqual(find_aux_object_search_match(self.run, 'T Tau'), 'V* T Tau')
        qs = ObservationRun.objects.filter(build_run_aux_objects_search_q('T Tau'))
        self.assertIn(self.run, qs)
        response = self.client.get('/api/runs/runs/', {'aux_object': 'T Tau'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pks = {item['pk'] for item in response.data['results']}
        self.assertIn(self.run.pk, pks)
        match = next(item for item in response.data['results'] if item['pk'] == self.run.pk)
        self.assertEqual(match['search_match_via_aux'], 'V* T Tau')
