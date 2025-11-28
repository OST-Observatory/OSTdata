from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from obs_run.models import ObservationRun


class RunsApiETagTest(APITestCase):
    def setUp(self):
        ObservationRun.objects.create(name='Test Run', is_public=True, mid_observation_jd=2451546.0)

    def test_list_etag_304(self):
        url = '/api/runs/runs/'
        # First request to get ETag
        resp1 = self.client.get(url)
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        etag = resp1.headers.get('ETag') or resp1._headers.get('etag', [None, None])[1]
        self.assertTrue(etag)
        # Second request with If-None-Match should return 304
        resp2 = self.client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(resp2.status_code, status.HTTP_304_NOT_MODIFIED)


