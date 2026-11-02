"""Data-file list: fields come from the database, not from the files."""
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DataFile, ObservationRun


class DataFileListTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-03-08', is_public=True)
        DataFile.objects.create(
            observation_run=self.run, datafile='/nonexistent/dark_120s.fit', file_type='FITS',
            file_size=8, exposure_type='DA', binning_x=2, binning_y=2,
        )

    def test_binning_without_reading_the_fits_header(self):
        with patch.object(DataFile, 'get_fits_header',
                          side_effect=AssertionError('header read in a list view')):
            resp = self.client.get(
                '/api/runs/datafiles/',
                {'observation_run': self.run.pk, 'file_type': 'FITS', 'limit': 200},
            )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['results'][0]['binning'], '2x2')
