"""Canonical instrument names: aliases, geometry-based resolution, sync on save, backfill and filter."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run.analyze_fits_header import analyze_fits, canonical_instrument, detect_instruments
from obs_run.models import DataFile, ObservationRun
from obs_run.utils import INSTRUMENT_CATALOG, normalize_instrument

QHY600_GEOMETRY = {'naxis1': 9576, 'naxis2': 6388, 'pixel_size': 3.76}
QHY268_GEOMETRY = {'naxis1': 6252, 'naxis2': 4176, 'pixel_size': 3.76}


class CanonicalInstrumentTest(TestCase):
    def test_aliases(self):
        cases = {
            'QHY CCD QHY600M-62e19d4': 'QHY 600M',
            'QHY600M': 'QHY 600M',
            'SBIG ST-8 3 CCD Camera': 'SBIG ST-8',
            'SBIG ST7': 'SBIG ST-7',
            'SBIG STF-8300M': 'SBIG STF-8300',
            'ZWO ASI174MM Mini (ASCOM)': 'ZWO ASI174MM Mini',
            'Apogee USB/Net': 'Apogee USB/Net',  # no alias: kept
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical_instrument(raw), expected)

    def test_catalog_names_are_canonical(self):
        for item in INSTRUMENT_CATALOG:
            with self.subTest(name=item['name']):
                self.assertEqual(normalize_instrument(item['name']), item['name'])

    def test_missing_or_generic_names_resolved_from_geometry(self):
        self.assertEqual(canonical_instrument('UK', **QHY600_GEOMETRY), 'QHY 600M')
        # QHY 268M and ZWO ASI2600MC Pro share the sensor; the generic QHY header decides
        self.assertEqual(canonical_instrument('QHYCCD-Cameras-Capture', **QHY268_GEOMETRY), 'QHY 268M')
        self.assertEqual(canonical_instrument('UK'), 'Unknown')
        self.assertEqual(canonical_instrument('QHYCCD-Cameras-Capture'), 'QHY 600M or QHY 268M')

    def test_binned_geometry(self):
        # 3x3 binning of the QHY 600M: 3192 x 2129 px, XPIXSZ written binned (11.28) or unbinned (3.76)
        for pixel_size in (11.28, 3.76):
            with self.subTest(pixel_size=pixel_size):
                self.assertEqual(detect_instruments(3192, 2129, pixel_size, 3, 3), ['QHY 600M'])
                self.assertEqual(
                    canonical_instrument('QHYCCD-Cameras-Capture', 3192, 2129, pixel_size, 3, 3), 'QHY 600M',
                )
        # 2x2 binning of the QHY 268M
        self.assertEqual(canonical_instrument('QHYCCD-Cameras-Capture', 3126, 2088, 7.52, 2, 2), 'QHY 268M')

    def test_shared_sensor_resolved_by_generic_zwo_header(self):
        self.assertEqual(canonical_instrument('ASI Camera (1)', 6248, 4176, 3.76), 'ZWO ASI2600MC Pro')


class AnalyzeFitsInstrumentTest(TestCase):
    def _analyze(self, header_data):
        run = ObservationRun.objects.create(name='fits', is_public=True)
        datafile = DataFile.objects.create(observation_run=run, datafile='/tmp/frame.fits', file_type='FITS')
        with patch.object(DataFile, 'get_fits_header', return_value={}), \
                patch('obs_run.analyze_fits_header.extract_fits_header_info', return_value=header_data):
            analyze_fits(datafile)
        datafile.refresh_from_db()
        return datafile

    def test_generic_header_resolved_by_header_name_not_catalog_order(self):
        # QHY 268M comes first in the catalog and shares the sensor with the ZWO ASI2600MC Pro
        datafile = self._analyze({
            'instrument': 'ASI Camera (1)', 'naxis1': 6248, 'naxis2': 4176, 'pixel_size': 3.76,
            'binning_x': 1, 'binning_y': 1,
        })
        self.assertEqual(datafile.instrument, 'ZWO ASI2600MC Pro')
        self.assertEqual(datafile.instrument_normalized, 'ZWO ASI2600MC Pro')

    def test_specific_header_name_is_kept(self):
        datafile = self._analyze({
            'instrument': 'QHY600M', 'naxis1': 3192, 'naxis2': 2129, 'pixel_size': 11.28,
            'binning_x': 3, 'binning_y': 3,
        })
        self.assertEqual(datafile.instrument, 'QHY600M')
        self.assertEqual(datafile.instrument_normalized, 'QHY 600M')


class InstrumentApiDisplayTest(APITestCase):
    def test_generic_raw_name_displayed_as_resolved_camera(self):
        run = ObservationRun.objects.create(name='display', is_public=True)
        DataFile.objects.create(
            observation_run=run, datafile='/tmp/g.fit', file_type='FITS', instrument='QHYCCD-Cameras-Capture',
            naxis1=3192, naxis2=2129, pixel_size=11.28, binning_x=3, binning_y=3,
        )
        row = self.client.get('/api/runs/datafiles/').json()['results'][0]
        self.assertEqual(row['instrument'], 'QHY 600M')
        self.assertEqual(row['instrument_normalized'], 'QHY 600M')


class InstrumentNormalizedFieldTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='cams', is_public=True)

    def _file(self, instrument, **kwargs):
        return DataFile.objects.create(
            observation_run=self.run, datafile=f'/tmp/{DataFile.objects.count()}.fit', file_type='FITS',
            instrument=instrument, **kwargs,
        )

    def test_kept_in_sync_on_save(self):
        datafile = self._file('QHY600M')
        self.assertEqual(datafile.instrument_normalized, 'QHY 600M')
        datafile.instrument = 'QHY CCD QHY268M-92149f4'
        datafile.save(update_fields=['instrument'])
        datafile.refresh_from_db()
        self.assertEqual(datafile.instrument_normalized, 'QHY 268M')

    def test_backfill_command(self):
        datafile = self._file('QHYCCD-Cameras-Capture', **QHY600_GEOMETRY)
        DataFile.objects.filter(pk=datafile.pk).update(instrument_normalized='')

        out = StringIO()
        call_command('normalize_instruments', '--dry-run', stdout=out)
        self.assertIn('1 files would change', out.getvalue())
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).instrument_normalized, '')

        call_command('normalize_instruments', stdout=StringIO())
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).instrument_normalized, 'QHY 600M')


class InstrumentFilterTest(APITestCase):
    def test_filter_matches_raw_and_canonical_name(self):
        run = ObservationRun.objects.create(name='public', is_public=True)
        raw = DataFile.objects.create(observation_run=run, datafile='/tmp/a.fit', file_type='FITS', instrument='QHY600M')
        DataFile.objects.create(observation_run=run, datafile='/tmp/b.fit', file_type='FITS', instrument='QHY268M')

        for value in ('QHY 600M', 'qhy600'):
            with self.subTest(value=value):
                response = self.client.get('/api/runs/datafiles/', {'instrument': value})
                self.assertEqual([row['pk'] for row in response.json()['results']], [raw.pk])
