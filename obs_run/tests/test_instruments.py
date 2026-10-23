"""Canonical instrument names: aliases, geometry-based resolution, sync on save, backfill and filter."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run.analyze_fits_header import (
    analyze_fits,
    canonical_instrument,
    detect_instruments,
    extract_fits_header_info,
)
from obs_run.analyze_image_and_video_header import analyze_ser, ser_camera_name, ser_color_sensor
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

    def test_catalog_declares_sensor_type(self):
        for item in INSTRUMENT_CATALOG:
            with self.subTest(name=item['name']):
                self.assertIsInstance(item.get('color'), bool)

    def test_sensor_type_resolves_shared_geometry(self):
        # QHY 268M (mono) and ZWO ASI2600MC Pro (color) share the sensor
        self.assertEqual(detect_instruments(6248, 4176, -1, 1, 1), ['QHY 268M', 'ZWO ASI2600MC Pro'])
        self.assertEqual(detect_instruments(6248, 4176, -1, 1, 1, color=True), ['ZWO ASI2600MC Pro'])
        self.assertEqual(detect_instruments(6248, 4176, -1, 1, 1, color=False), ['QHY 268M'])
        self.assertEqual(canonical_instrument('', 6248, 4176, -1, 1, 1, color=True), 'ZWO ASI2600MC Pro')
        # ZWO ASI220MM (mono) and QHY 5III462C (color): both 1920 x 1080, no pixel size in SER files
        self.assertEqual(canonical_instrument('', 1920, 1080, -1, 1, 1, color=True), 'QHY 5III462C')
        self.assertEqual(canonical_instrument('', 1920, 1080, -1, 1, 1, color=False), 'ZWO ASI220MM')

    def test_contradicting_sensor_type_keeps_geometry_match(self):
        # e.g. color data from a mono-only geometry: do not drop the only match
        self.assertEqual(detect_instruments(9576, 6388, 3.76, 1, 1, color=True), ['QHY 600M'])

    def test_fits_bayer_pattern_marks_color_sensor(self):
        self.assertIs(extract_fits_header_info({'BAYERPAT': 'RGGB'})['color_sensor'], True)
        # Missing keyword does not prove a mono sensor
        self.assertIsNone(extract_fits_header_info({})['color_sensor'])


class SerCameraTest(TestCase):
    def test_header_helpers(self):
        self.assertEqual(ser_camera_name('ZWO ASI174MM' + '\x00' * 28), 'ZWO ASI174MM')
        self.assertEqual(ser_camera_name(''), '')
        self.assertIs(ser_color_sensor(0), False)
        self.assertIs(ser_color_sensor(8), True)
        self.assertIs(ser_color_sensor(100), True)
        self.assertIsNone(ser_color_sensor(42))

    def _analyze(self, header):
        run = ObservationRun.objects.create(name='ser', is_public=True)
        datafile = DataFile.objects.create(observation_run=run, datafile='/tmp/clip.ser', file_type='SER')
        with patch('obs_run.analyze_image_and_video_header.SERParser') as parser_cls:
            parser_cls.return_value.header = {'ImageWidth': 1920, 'ImageHeight': 1080, **header}
            analyze_ser(datafile)
        datafile.refresh_from_db()
        return datafile

    def test_camera_name_and_sensor_type_from_header(self):
        datafile = self._analyze({'Instrument': 'ZWO ASI174MM'.ljust(40, '\x00'), 'ColorID': 0})
        self.assertEqual(datafile.instrument, 'ZWO ASI174MM')
        self.assertIs(datafile.color_sensor, False)
        self.assertEqual(datafile.instrument_normalized, 'ZWO ASI174MM')

    def test_shared_geometry_resolved_by_color_id(self):
        datafile = self._analyze({'Instrument': '', 'ColorID': 8})
        self.assertIs(datafile.color_sensor, True)
        self.assertEqual(datafile.instrument_normalized, 'QHY 5III462C')


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


class BackfillCameraInfoTest(TestCase):
    CMD = 'obs_run.management.commands.backfill_camera_info'

    def setUp(self):
        self.run = ObservationRun.objects.create(name='backfill', is_public=True)

    def _file(self, name, file_type, **kwargs):
        return DataFile.objects.create(
            observation_run=self.run, datafile=f'/tmp/{name}', file_type=file_type, main_target='M 42', **kwargs,
        )

    def _run(self, *args):
        out = StringIO()
        call_command('backfill_camera_info', *args, stdout=out)
        return out.getvalue()

    def test_fills_camera_fields_only(self):
        fits_file = self._file('a.fits', 'FITS', naxis1=6248, naxis2=4176)
        ser_file = self._file('b.ser', 'SER', naxis1=1920, naxis2=1080)
        avi_file = self._file('c.avi', 'AVI')
        self.assertEqual(fits_file.instrument_normalized, 'QHY 268M')  # shared sensor, first guess

        with patch.object(DataFile, 'get_fits_header', return_value={'BAYERPAT': 'RGGB'}), \
                patch(f'{self.CMD}.read_ser_header', return_value={'Instrument': 'ZWO ASI174MM', 'ColorID': 0}), \
                patch(f'{self.CMD}.video_frame_size', return_value=(1936, 1216)):
            output = self._run()
        self.assertIn('3 files updated', output)

        fits_file.refresh_from_db()
        self.assertIs(fits_file.color_sensor, True)
        self.assertEqual(fits_file.instrument_normalized, 'ZWO ASI2600MC Pro')
        ser_file.refresh_from_db()
        self.assertEqual((ser_file.instrument, ser_file.color_sensor), ('ZWO ASI174MM', False))
        avi_file.refresh_from_db()
        self.assertEqual((avi_file.naxis1, avi_file.naxis2), (1936, 1216))
        self.assertEqual(avi_file.instrument_normalized, 'ZWO ASI174MM')
        for datafile in (fits_file, ser_file, avi_file):
            self.assertEqual(datafile.main_target, 'M 42')

    def test_dry_run_and_protected_instrument(self):
        ser_file = self._file('d.ser', 'SER', instrument='My camera', instrument_override=True)
        with patch(f'{self.CMD}.read_ser_header', return_value={'Instrument': 'ZWO ASI174MM', 'ColorID': 8}):
            self.assertIn('DRY RUN: 1 files would change', self._run('--kind', 'ser', '--dry-run'))
            ser_file.refresh_from_db()
            self.assertIsNone(ser_file.color_sensor)

            self._run('--kind', 'ser')
        ser_file.refresh_from_db()
        self.assertEqual((ser_file.instrument, ser_file.color_sensor), ('My camera', True))
