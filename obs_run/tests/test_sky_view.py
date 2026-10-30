"""Sky view: preview WCS, objects in the field, image size consistency, access control."""
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from django.conf import settings
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APITestCase

from objects.models import Object
from obs_run.models import DataFile, ObservationRun
from obs_run.sky_view import covered_size, datafile_wcs_header, scaled_wcs

# 4000 x 3000 px, 1"/px, rotated by 30 deg
_SCALE = 1 / 3600
_ROT = np.radians(30)
FULL = {
    'NAXIS1': 4000, 'NAXIS2': 3000, 'CTYPE1': 'RA---TAN', 'CTYPE2': 'DEC--TAN',
    'CRVAL1': 83.82, 'CRVAL2': -5.39, 'CRPIX1': 1800.5, 'CRPIX2': 1400.5,
    'CD1_1': -_SCALE * np.cos(_ROT), 'CD1_2': _SCALE * np.sin(_ROT),
    'CD2_1': _SCALE * np.sin(_ROT), 'CD2_2': _SCALE * np.cos(_ROT),
}


def _wcs(header):
    return WCS({k: v for k, v in header.items()}, naxis=2)


class ScaledWcsTest(TestCase):
    def test_preview_pixels_point_to_the_same_sky_positions(self):
        for width, height in ((1000, 750), (2048, 1536), (1001, 749)):
            with self.subTest(size=(width, height)):
                small = scaled_wcs(FULL, width, height)
                sx, sy = width / FULL['NAXIS1'], height / FULL['NAXIS2']
                # Corners, centre and an arbitrary pixel of the full image (FITS 1-based)
                for x, y in ((1, 1), (4000, 3000), (1, 3000), (2000.5, 1500.5), (123.4, 2876.9)):
                    full_sky = _wcs(FULL).all_pix2world([[x, y]], 1)[0]
                    small_sky = _wcs(small).all_pix2world([[(x - 0.5) * sx + 0.5, (y - 0.5) * sy + 0.5]], 1)[0]
                    np.testing.assert_allclose(small_sky, full_sky, atol=1e-9)

    def test_cropped_blocks_keep_the_edges_exact(self):
        # 4001 x 3003 px averaged in 3 x 3 blocks (max_dim 1024): 4000 x 3003 px covered, 1333 x 1001 preview
        header = {**FULL, 'NAXIS1': 4001, 'NAXIS2': 3003}
        covered = covered_size(4001, 3003, 1024)
        self.assertEqual(covered, (3999, 3003))
        small = scaled_wcs(header, 1333, 1001, covered)
        # Outer edges of the preview = outer edges of the covered pixels
        for (px, py), (fx, fy) in (((0.5, 0.5), (0.5, 0.5)), ((1333.5, 1001.5), (3999.5, 3003.5))):
            np.testing.assert_allclose(
                _wcs(small).all_pix2world([[px, py]], 1)[0], _wcs(header).all_pix2world([[fx, fy]], 1)[0], atol=1e-9,
            )


class SkyViewApiTest(APITestCase):
    def setUp(self):
        root = Path(settings.DATA_DIRECTORY)
        root.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(dir=root)) / 'm42.fits'
        fits.PrimaryHDU(np.random.default_rng(1).normal(1000, 20, (300, 400)).astype(np.float32)).writeto(path)
        self.run = ObservationRun.objects.create(
            name='2026-10-30', is_public=True,
            aux_objects=[
                {'name': 'Inside star', 'ra': 83.82, 'dec': -5.39, 'object_type': 'ST', 'v_mag': 9.1},
                {'name': 'Far away', 'ra': 10.0, 'dec': 41.0, 'object_type': 'GA', 'v_mag': 3.4},
            ],
        )
        # 400 x 300 px at 10"/px: about 1.1 x 0.8 deg around M42
        wcs = {'crval1': 83.82, 'crval2': -5.39, 'crpix1': 200.5, 'crpix2': 150.5,
               'cd1_1': -10 / 3600, 'cd1_2': 0.0, 'cd2_1': 0.0, 'cd2_2': 10 / 3600}
        self.datafile = DataFile.objects.create(
            observation_run=self.run, datafile=str(path), file_type='FITS', naxis1=400, naxis2=300,
            plate_solved=True, content_hash='sky-test', **{f'wcs_{k}': v for k, v in wcs.items()},
        )
        main = Object.objects.create(name='M 42', is_public=True, object_type='NE', ra=83.85, dec=-5.40)
        main.datafiles.add(self.datafile)

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    def test_sky_view_matches_the_image(self):
        data = self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/sky/?w=256').json()
        self.assertTrue(data['available'])
        image = self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/sky/image/?w=256')
        self.assertEqual(image['Content-Type'], 'image/jpeg')
        with Image.open(BytesIO(image.content)) as img:
            self.assertEqual((data['wcs']['NAXIS1'], data['wcs']['NAXIS2']), img.size)
        versioned = self.client.get(
            f'/api/runs/datafiles/{self.datafile.pk}/sky/image/?w=256&v={data["image_version"]}',
        )
        self.assertIn('immutable', versioned['Cache-Control'])
        names = [(o['name'], o['main']) for o in data['objects']]
        self.assertEqual(names, [('M 42', True), ('Inside star', False)])
        self.assertAlmostEqual(data['center']['ra'], 83.82, places=6)

    def test_not_plate_solved_and_private_runs(self):
        DataFile.objects.filter(pk=self.datafile.pk).update(plate_solved=False)
        self.datafile.refresh_from_db()
        self.assertIsNone(datafile_wcs_header(self.datafile))
        self.assertFalse(self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/sky/').json()['available'])

        ObservationRun.objects.filter(pk=self.run.pk).update(is_public=False)
        self.assertEqual(self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/sky/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/runs/datafiles/{self.datafile.pk}/sky/image/').status_code, 404)


class SkyViewBlockAveragingTest(APITestCase):
    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    def test_reduced_image_still_matches_its_wcs(self):
        root = Path(settings.DATA_DIRECTORY)
        root.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(dir=root)) / 'big.fits'
        data = np.random.default_rng(2).normal(1000, 20, (703, 1101)).astype(np.float32)
        data[5, 7] = np.nan  # NaN handling of the block averaging
        fits.PrimaryHDU(data).writeto(path)
        run = ObservationRun.objects.create(name='2026-10-31', is_public=True)
        datafile = DataFile.objects.create(
            observation_run=run, datafile=str(path), file_type='FITS', naxis1=1101, naxis2=703, plate_solved=True,
            content_hash='big', wcs_crval1=10.0, wcs_crval2=20.0, wcs_crpix1=550.5, wcs_crpix2=351.5,
            wcs_cd1_1=-1 / 3600, wcs_cd1_2=0.0, wcs_cd2_1=0.0, wcs_cd2_2=1 / 3600,
        )
        view = self.client.get(f'/api/runs/datafiles/{datafile.pk}/sky/?w=256').json()
        image = self.client.get(f'/api/runs/datafiles/{datafile.pk}/sky/image/?w=256')
        with Image.open(BytesIO(image.content)) as img:
            self.assertEqual((view['wcs']['NAXIS1'], view['wcs']['NAXIS2']), img.size)
        # 4 x 4 blocks over 1100 x 700 px: the preview spans exactly that part of the image
        header = datafile_wcs_header(datafile)
        np.testing.assert_allclose(
            _wcs(view['wcs']).all_pix2world([[img.size[0] + 0.5, img.size[1] + 0.5]], 1)[0],
            _wcs(header).all_pix2world([[1100.5, 700.5]], 1)[0], atol=1e-9,
        )
