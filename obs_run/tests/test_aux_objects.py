"""Tests for SIMBAD auxiliary objects on observation runs."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.table import Table
from astropy.table import Table
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.aux_objects import (
    _field_diameter_deg,
    _fov_from_chip_and_telescope,
    _pair_cluster_threshold_deg,
    cluster_light_fits_by_pointing,
    compute_aux_objects,
    find_representative_light_fits,
    get_lookup_center_and_fov,
    normalize_simbad_objects,
)
from obs_run.models import DataFile, ObservationRun

User = get_user_model()


def _make_simbad_table():
  return Table({
      'main_id': ['HD 1', 'M 31', 'NGC 9999'],
      'ra': [10.0, 10.01, 10.5],
      'dec': [20.0, 20.01, 20.5],
      'alltypes.otypes': ['*', '|G|', 'ISM'],
      'V': [8.5, 9.0, np.nan],
  })


class AuxObjectsComputeTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2024-01-01_test', is_public=True, photometry=True)
        self.tmp_dir = tempfile.mkdtemp()
        self.fits_path = Path(self.tmp_dir) / 'light.fits'
        self.fits_path.write_bytes(b'PLACEHOLDER')
        self.df = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(self.fits_path),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            naxis1=2048,
            naxis2=2048,
            ra=10.0,
            dec=20.0,
            fov_x=0.5,
            fov_y=0.4,
            plate_solved=True,
            wcs_ra=10.0,
            wcs_dec=20.0,
        )

    def test_find_representative_light_fits_prefers_plate_solved(self):
        other = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(Path(self.tmp_dir) / 'other.fits'),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=1.0,
            dec=2.0,
        )
        rep = find_representative_light_fits(self.run)
        self.assertEqual(rep.pk, self.df.pk)
        self.assertNotEqual(rep.pk, other.pk)

    def test_get_lookup_center_and_fov_uses_wcs(self):
        ra, dec, fov_x, fov_y, radius = get_lookup_center_and_fov(self.df)
        self.assertEqual(ra, 10.0)
        self.assertEqual(dec, 20.0)
        self.assertEqual(fov_x, 0.5)
        self.assertEqual(fov_y, 0.4)
        self.assertGreater(radius, 0)

    def test_normalize_simbad_objects_excludes_main_target(self):
        table = _make_simbad_table()
        objects = normalize_simbad_objects(
            table,
            center_ra=10.0,
            center_dec=20.0,
            main_names={'HD 1'},
            main_coords=[],
        )
        names = {obj['name'] for obj in objects}
        self.assertNotIn('HD 1', names)
        self.assertIn('M 31', names)
        self.assertEqual(objects[0]['object_type_display'], 'Galaxy')

    @patch('obs_run.aux_objects.filter_table_to_footprint', side_effect=lambda t, _df: t)
    @patch('obs_run.aux_objects._query_region_safe')
    def test_compute_aux_objects(self, query_mock, _filter_mock):
        query_mock.return_value = _make_simbad_table()
        result = compute_aux_objects(self.run)
        self.assertEqual(result['meta']['source_datafile_id'], self.df.pk)
        self.assertEqual(result['meta']['cluster_count'], 1)
        self.assertGreaterEqual(len(result['objects']), 1)
        query_mock.assert_called_once()

    @override_settings(AUX_OBJECTS_CLUSTER_SEPARATION_DEG=1.0)
    def test_cluster_groups_nearby_pointings(self):
        near = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(Path(self.tmp_dir) / 'near.fits'),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=10.002,
            dec=20.002,
            fov_x=0.5,
            fov_y=0.4,
        )
        clusters = cluster_light_fits_by_pointing([self.df, near])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    @override_settings(AUX_OBJECTS_CLUSTER_SEPARATION_DEG=1.0)
    def test_cluster_splits_distant_pointings(self):
        far = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(Path(self.tmp_dir) / 'far.fits'),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=15.0,
            dec=25.0,
            fov_x=0.5,
            fov_y=0.4,
        )
        clusters = cluster_light_fits_by_pointing([self.df, far])
        self.assertEqual(len(clusters), 2)

    def test_fov_from_chip_and_telescope(self):
        chip_df = DataFile(
            naxis1=4096,
            naxis2=4096,
            pixel_size=9.0,  # µm
            focal_length=3000.0,  # mm
        )
        fov = _fov_from_chip_and_telescope(chip_df)
        self.assertIsNotNone(fov)
        fov_x, fov_y = fov
        self.assertGreater(fov_x, 0.1)
        self.assertGreater(fov_y, 0.1)

    def test_pair_cluster_threshold_uses_smaller_field_diameter(self):
        small_field = DataFile(fov_x=0.2, fov_y=0.2)
        large_field = DataFile(fov_x=2.0, fov_y=2.0)
        threshold = _pair_cluster_threshold_deg(small_field, large_field)
        small_diam = _field_diameter_deg(small_field)
        self.assertAlmostEqual(threshold, 0.5 * small_diam, places=5)

    @override_settings(AUX_OBJECTS_CLUSTER_SEPARATION_DEG=1.0)
    @patch('obs_run.aux_objects.filter_table_to_footprint', side_effect=lambda t, _df: t)
    @patch('obs_run.aux_objects._query_region_safe')
    def test_compute_aux_objects_multiple_clusters(self, query_mock, _filter_mock):
        query_mock.return_value = _make_simbad_table()
        DataFile.objects.create(
            observation_run=self.run,
            datafile=str(Path(self.tmp_dir) / 'field2.fits'),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=15.0,
            dec=25.0,
            fov_x=0.5,
            fov_y=0.4,
        )
        result = compute_aux_objects(self.run)
        self.assertEqual(result['meta']['cluster_count'], 2)
        self.assertEqual(query_mock.call_count, 2)

    @patch('obs_run.aux_objects._query_region_safe')
    def test_compute_aux_objects_applies_footprint_filter(self, query_mock):
        query_mock.return_value = Table({
            'main_id': ['center', 'far'],
            'ra': [10.0, 10.0],
            'dec': [20.0, 25.0],
            'alltypes.otypes': ['*', '*'],
            'V': [10.0, 11.0],
        })
        result = compute_aux_objects(self.run)
        names = {obj['name'] for obj in result['objects']}
        self.assertIn('center', names)
        self.assertNotIn('far', names)
        self.assertEqual(result['meta']['simbad_match_count'], 2)
        self.assertEqual(result['meta']['fov_filtered_count'], 1)


class AuxObjectsApiTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2024-02-01_test', is_public=True, photometry=True)
        self.tmp_dir = tempfile.mkdtemp()
        self.fits_path = Path(self.tmp_dir) / 'light.fits'
        self.fits_path.write_bytes(b'PLACEHOLDER')
        DataFile.objects.create(
            observation_run=self.run,
            datafile=str(self.fits_path),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=10.0,
            dec=20.0,
            fov_x=0.5,
            fov_y=0.4,
        )
        self.url = f'/api/runs/runs/{self.run.pk}/aux-objects/'

    @patch('obs_run.aux_objects.compute_aux_objects')
    def test_public_run_aux_objects_compute_and_cache(self, compute_mock):
        compute_mock.return_value = {
            'objects': [{'name': 'M 31', 'ra': 10.1, 'dec': 20.1, 'object_type': 'GA'}],
            'meta': {'source_datafile_id': 1, 'center_ra': 10.0, 'center_dec': 20.0},
        }

        resp1 = self.client.get(self.url)
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp1.data['status'], 'ready')
        self.assertEqual(len(resp1.data['objects']), 1)
        compute_mock.assert_called_once()

        compute_mock.reset_mock()
        resp2 = self.client.get(self.url)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data['status'], 'ready')
        compute_mock.assert_not_called()

    @patch('obs_run.aux_objects.compute_aux_objects')
    def test_refresh_forces_recompute(self, compute_mock):
        compute_mock.return_value = {
            'objects': [],
            'meta': {},
        }
        self.client.get(self.url)
        compute_mock.reset_mock()
        self.client.get(f'{self.url}?refresh=1')
        compute_mock.assert_called_once()

    def test_non_photometry_run_rejected(self):
        self.run.photometry = False
        self.run.save(update_fields=['photometry'])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('obs_run.aux_objects.compute_aux_objects')
    def test_private_run_requires_read_permission(self, compute_mock):
        compute_mock.return_value = {'objects': [], 'meta': {}}
        private_run = ObservationRun.objects.create(name='2024-02-02_priv', is_public=False, photometry=True)
        fits = Path(self.tmp_dir) / 'private.fits'
        fits.write_bytes(b'x')
        DataFile.objects.create(
            observation_run=private_run,
            datafile=str(fits),
            file_type='FITS',
            exposure_type='LI',
            exposure_type_ml=None,
            ra=1.0,
            dec=2.0,
            fov_x=0.2,
            fov_y=0.2,
        )
        url = f'/api/runs/runs/{private_run.pk}/aux-objects/'

        anon = self.client.get(url)
        self.assertEqual(anon.status_code, status.HTTP_404_NOT_FOUND)

        user = User.objects.create_user(username='reader', password='pass')
        private_run.readonly_users.add(user)
        self.client.force_login(user)
        ok = self.client.get(url)
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
