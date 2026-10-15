"""Canonical instrument names: aliases, geometry-based resolution, sync on save, backfill and filter."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run.analyze_fits_header import canonical_instrument
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
