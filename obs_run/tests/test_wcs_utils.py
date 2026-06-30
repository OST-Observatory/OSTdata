"""Tests for DataFile WCS footprint helpers."""
from astropy.table import Table
from django.test import SimpleTestCase

from obs_run.models import DataFile
from obs_run.wcs_utils import (
    build_wcs_from_datafile,
    coords_inside_footprint,
    filter_table_to_footprint,
    has_plate_solve_wcs,
)


class WcsUtilsTest(SimpleTestCase):
    def test_has_plate_solve_wcs_requires_crval_and_crpix(self):
        df = DataFile(
            plate_solved=True,
            naxis1=1024,
            naxis2=1024,
            wcs_crval1=150.0,
            wcs_crval2=2.0,
            wcs_crpix1=512.0,
            wcs_crpix2=512.0,
            wcs_cd1_1=-0.0001,
            wcs_cd1_2=0.0,
            wcs_cd2_1=0.0,
            wcs_cd2_2=0.0001,
        )
        self.assertTrue(has_plate_solve_wcs(df))

    def test_build_wcs_prefers_plate_solve_matrix(self):
        df = DataFile(
            plate_solved=True,
            naxis1=100,
            naxis2=100,
            wcs_crval1=10.0,
            wcs_crval2=20.0,
            wcs_crpix1=50.0,
            wcs_crpix2=50.0,
            wcs_cd1_1=-0.001,
            wcs_cd1_2=0.0,
            wcs_cd2_1=0.0,
            wcs_cd2_2=0.001,
        )
        built = build_wcs_from_datafile(df)
        self.assertIsNotNone(built)
        wcs_obj, n1, n2 = built
        self.assertEqual(n1, 100)
        inside = coords_inside_footprint([10.0], [20.0], wcs_obj, n1, n2)
        self.assertTrue(bool(inside[0]))

    def test_filter_table_to_footprint_drops_off_chip_objects(self):
        df = DataFile(
            naxis1=1000,
            naxis2=1000,
            ra=10.0,
            dec=20.0,
            fov_x=0.2,
            fov_y=0.2,
        )
        table = Table({
            'main_id': ['center', 'far'],
            'ra': [10.0, 10.0],
            'dec': [20.0, 25.0],
        })
        filtered = filter_table_to_footprint(table, df)
        names = set(filtered['main_id'])
        self.assertIn('center', names)
        self.assertNotIn('far', names)

    @staticmethod
    def _make_solved_df():
        return DataFile(
            plate_solved=True,
            naxis1=2000,
            naxis2=2000,
            wcs_crval1=83.0,
            wcs_crval2=-5.0,
            wcs_crpix1=1000.0,
            wcs_crpix2=1000.0,
            wcs_cd1_1=-0.0002,
            wcs_cd1_2=0.0,
            wcs_cd2_1=0.0,
            wcs_cd2_2=0.0002,
            ra=83.0,
            dec=-5.0,
            fov_x=0.4,
            fov_y=0.4,
        )

    def test_filter_table_with_plate_solve_wcs(self):
        df = self._make_solved_df()
        table = Table({
            'main_id': ['on', 'off'],
            'ra': [83.0, 90.0],
            'dec': [-5.0, -5.0],
        })
        filtered = filter_table_to_footprint(table, df)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered['main_id'][0], 'on')
