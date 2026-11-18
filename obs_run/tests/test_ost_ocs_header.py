"""Header keywords of OST_OCS files: Arc Frame / Dark Flat, SPECTRO, FILTER, canonical camera names."""
import tempfile
from io import StringIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from django.core.management import call_command
from django.test import TestCase

from obs_run.analyze_fits_header import analyze_fits, detect_instruments, extract_fits_header_info
from obs_run.exposure_type import classifier_class_name, valid_combination
from obs_run.filter_names import FILTER_ALIASES, _key, normalize_filter
from obs_run.ml_classification import apply_ml_result
from obs_run.models import DataFile, ObservationRun
from obs_run.spectrograph import automatic_spectrograph, header_spectrograph
from obs_run.spectrograph_heuristics import analyse
from obs_run.tests.test_reanalyze_fits import fits_header
from obs_run.tests.test_spectrograph_suggestions import _file
from obs_run.utils import normalize_instrument

OST_OCS = 'OST_OCS 0.3.1'


def _header(**cards):
    header = fits.Header()
    for key, value in cards.items():
        header[key] = value
    return header


class HeaderKeywordTest(TestCase):
    def test_spectro_only_trusted_from_ost_ocs(self):
        cases = [
            ({'SWCREATE': OST_OCS, 'SPECTRO': 'BACHES'}, 'B'),
            ({'SWCREATE': OST_OCS, 'SPECTRO': 'DADOS'}, 'D'),
            ({'SWCREATE': OST_OCS, 'SPECTRO': 'uvex '}, 'U'),
            ({'SWCREATE': OST_OCS, 'SPECTRO': 'NONE'}, 'N'),
            ({'SWCREATE': OST_OCS, 'SPECTRO': 'LHIRES'}, None),  # unknown value
            ({'SWCREATE': OST_OCS}, None),
            ({'SWCREATE': 'N.I.N.A. 3.1', 'SPECTRO': 'BACHES'}, None),  # other software: not reliable
            ({'SPECTRO': 'BACHES'}, None),
        ]
        for cards, expected in cases:
            with self.subTest(cards=cards):
                self.assertEqual(header_spectrograph(_header(**cards)), expected)
                self.assertEqual(extract_fits_header_info(_header(**cards))['spectrograph_header'], expected)

    def test_filter(self):
        cases = [('SLOAN-r', 'SLOAN-r'), (' Ha ', 'Ha'), ('V', 'V'), ('**LEER**', ''), ('** LEER **', ''), ('-', ''), ('H-Alpha', 'H-Alpha'), ('', ''), (None, '')]
        for value, expected in cases:
            with self.subTest(value=value):
                header = _header() if value is None else _header(FILTER=value)
                self.assertEqual(extract_fits_header_info(header)['image_filter'], expected)


class AnalyzeOstOcsFileTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-10-22')
        self.datafile = DataFile.objects.create(
            observation_run=self.run, datafile='/tmp/2026-10-22/QHY268M_BACHES/arc/a.fits', file_type='FITS',
        )

    def _analyze(self, **header):
        with fits_header({'naxis1': 100, 'naxis2': 100, **header}):
            analyze_fits(self.datafile)
        self.datafile.refresh_from_db()
        return self.datafile

    def test_arc_frame_and_dark_flat(self):
        self.assertEqual(self._analyze(imagetyp='Arc Frame').exposure_type, 'WA')
        self.assertEqual(self._analyze(imagetyp='Dark Flat').exposure_type, 'DA')
        self.assertEqual(DataFile(exposure_type='WA').get_exposure_type_display(), 'Arc Frame')

    def test_spectrograph_and_filter_from_header(self):
        datafile = self._analyze(imagetyp='Arc Frame', spectrograph_header='U', image_filter='Clear')
        self.assertEqual((datafile.spectrograph, datafile.spectrograph_header), ('U', 'U'))
        self.assertEqual(datafile.image_filter, 'Clear')

    def test_darks_carry_no_spectrograph(self):
        datafile = self._analyze(imagetyp='Dark Frame', spectrograph_header='B')
        self.assertEqual((datafile.spectrograph, datafile.spectrograph_header), ('N', 'B'))

    def test_manual_spectrograph_wins(self):
        DataFile.objects.filter(pk=self.datafile.pk).update(spectrograph='D', spectrograph_override=True)
        self.datafile.refresh_from_db()
        self.assertEqual(self._analyze(imagetyp='Light Frame', spectrograph_header='B').spectrograph, 'D')

    def test_files_of_other_software_keep_spectrograph(self):
        DataFile.objects.filter(pk=self.datafile.pk).update(spectrograph='B')
        self.datafile.refresh_from_db()
        datafile = self._analyze(imagetyp='Light Frame', spectrograph_header=None)
        self.assertEqual((datafile.spectrograph, datafile.spectrograph_header), ('B', None))

    def test_header_wins_over_classifier(self):
        datafile = DataFile(exposure_type='LI', instrument='QHY268M', spectrograph_header='B')
        self.assertEqual(automatic_spectrograph(datafile, 'D'), 'B')
        apply_ml_result(datafile, {'exposure_type_ml': 'LI', 'spectrograph_ml': 'D'})
        self.assertEqual((datafile.spectrograph, datafile.spectrograph_ml), ('B', 'D'))

    def test_no_heuristic_suggestion_for_header_value(self):
        run = ObservationRun.objects.create(name='baches-night')
        for _ in range(15):
            _file(run, 'B')
        outlier = _file(run, 'N')
        from_header = _file(run, 'N', spectrograph_header='N')
        suggestions = analyse()['suggestions']
        self.assertIn(outlier.pk, suggestions)
        self.assertNotIn(from_header.pk, suggestions)


class UvexAndCameraTest(TestCase):
    def test_uvex_is_valid_but_no_classifier_class(self):
        for exposure_type in ('LI', 'FL', 'WA'):
            self.assertTrue(valid_combination(exposure_type, 'U'))
            self.assertIsNone(classifier_class_name(exposure_type, 'U'))
        self.assertFalse(valid_combination('DA', 'U'))
        self.assertIn(('U', 'UVEX'), DataFile.spectrograph_possibilities)

    def test_canonical_camera_names(self):
        cases = [
            ('QHY600M', 'QHY 600M'),
            ('QHY600M-PRO-L', 'QHY 600M'),
            ('qhy-600m', 'QHY 600M'),
            ('QHY268M', 'QHY 268M'),
            ('veTEC533C', 'omegon veTEC 533C'),
            ('ASI2600MC-Pro', 'ZWO ASI2600MC Pro'),
            ('QHYCCD-Cameras-Capture', 'QHY 600M or QHY 268M'),
            ('Some Camera', 'Some Camera'),
        ]
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(normalize_instrument(name), expected)

    def test_overscan_geometry(self):
        self.assertEqual(detect_instruments(9600, 6422, 3.76, 1, 1), ['QHY 600M'])
        self.assertEqual(detect_instruments(9576, 6388, 3.76, 1, 1), ['QHY 600M'])
        self.assertIn('QHY 268M', detect_instruments(6280, 4210, 3.76, 1, 1))


class BackfillFiltersCommandTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = ObservationRun.objects.create(name='2024-05-01')

    def _datafile(self, name, filter_value=None, **fields):
        path = Path(self.tmp.name) / name
        header = fits.Header()
        if filter_value is not None:
            header['FILTER'] = filter_value
        header['OBJCTRA'] = '00 42 44'  # differs from the stored (manually corrected) position
        fits.PrimaryHDU(np.zeros((4, 4), dtype=np.uint16), header=header).writeto(path)
        return DataFile.objects.create(
            observation_run=self.run, datafile=str(path), file_type='FITS', ra=10.5, dec=41.2, **fields,
        )

    def _call(self, *args):
        out = StringIO()
        call_command('backfill_filters', *args, stdout=out)
        return out.getvalue()

    def test_only_filter_is_written(self):
        sloan = self._datafile('a.fits', 'SLOAN-r', main_target='M 31', exposure_type_user='LI')
        placeholder = self._datafile('b.fits', '**LEER**')
        missing = DataFile.objects.create(observation_run=self.run, datafile='/nonexistent/c.fits', file_type='FITS')

        out = self._call('--dry-run')
        self.assertIn('DRY RUN: 1 files would change', out)
        self.assertIn('1 unreadable', out)
        self.assertEqual(DataFile.objects.get(pk=sloan.pk).image_filter, '')

        self._call()
        sloan.refresh_from_db()
        self.assertEqual(sloan.image_filter, 'SLOAN-r')
        self.assertEqual((sloan.ra, sloan.dec, sloan.main_target, sloan.exposure_type_user), (10.5, 41.2, 'M 31', 'LI'))
        self.assertEqual(sloan.history.latest().history_change_reason, 'task:backfill_filters')
        self.assertEqual(DataFile.objects.get(pk=placeholder.pk).image_filter, '')
        self.assertEqual(DataFile.objects.get(pk=missing.pk).image_filter, '')

    def test_existing_values_only_with_all(self):
        datafile = self._datafile('a.fits', 'V')
        DataFile.objects.filter(pk=datafile.pk).update(image_filter='R')
        self.assertIn('0 files read', self._call())
        self.assertIn("'R' -> 'V'", self._call('--all'))
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).image_filter, 'V')


class FilterNormalizationTest(TestCase):
    def test_archive_spellings(self):
        cases = [
            ('V', 'V'), ('B', 'B'), ('R', 'R'), ('I', 'I'), ('U', 'U'), ('Clear', 'Clear'),
            ('H alpha', 'Ha'), ('Halpha', 'Ha'), ('H-Alpha', 'Ha'), ('H_alpha', 'Ha'),
            ('OIII', 'OIII'), ('O III', 'OIII'), ('SII', 'SII'), ('S II', 'SII'), ('H-Beta', 'Hb'),
            ('Red', 'Red'), ('Green', 'Green'), ('Blue', 'Blue'), ('Luminance', 'Luminance'),
            ("g'", 'SLOAN-g'), ('g’', 'SLOAN-g'), ('SLOAN-r', 'SLOAN-r'),
            ('UV/IR', 'UV/IR-Cut'), ('BlockUV/IR', 'UV/IR-Cut'), ('UV Block', 'UV-Block'), ('LPR', 'LPR'),
            ('Slot 8', ''), ('Filter#1', ''), ('', ''), ('Some New Filter', 'Some New Filter'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_filter(raw), expected)

    def test_rgb_clear_and_uv_filters_stay_separate(self):
        self.assertNotEqual(normalize_filter('Red'), normalize_filter('R'))
        self.assertNotEqual(normalize_filter('Blue'), normalize_filter('B'))
        self.assertNotEqual(normalize_filter('Clear'), normalize_filter('UV/IR'))
        self.assertNotEqual(normalize_filter('UV Block'), normalize_filter('UV/IR'))

    def test_aliases_do_not_collide(self):
        # Case-insensitive keys: two aliases with the same key must map to the same name
        names = {}
        for alias, name in FILTER_ALIASES.items():
            key = _key(alias)
            self.assertEqual(names.setdefault(key, name), name, alias)

    def test_kept_in_sync_on_save(self):
        run = ObservationRun.objects.create(name='2024-05-02')
        datafile = DataFile.objects.create(observation_run=run, datafile='/tmp/x.fits', image_filter='H-Alpha')
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).filter_normalized, 'Ha')
        datafile.image_filter = 'O III'
        datafile.save(update_fields=['image_filter'])
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).filter_normalized, 'OIII')

    def test_normalize_filters_command(self):
        run = ObservationRun.objects.create(name='2024-05-03')
        datafile = DataFile.objects.create(observation_run=run, datafile='/tmp/y.fits', image_filter='Halpha')
        DataFile.objects.filter(pk=datafile.pk).update(filter_normalized='')  # e.g. before the migration
        out = StringIO()
        call_command('normalize_filters', '--dry-run', stdout=out)
        self.assertIn("'Halpha': '' -> 'Ha'", out.getvalue())
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).filter_normalized, '')
        call_command('normalize_filters', stdout=StringIO())
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).filter_normalized, 'Ha')

    def test_api_filter_finds_all_spellings(self):
        from obs_run.api.filter import DataFileFilter

        run = ObservationRun.objects.create(name='2024-05-04')
        files = {
            raw: DataFile.objects.create(observation_run=run, datafile=f'/tmp/{i}.fits', image_filter=raw)
            for i, raw in enumerate(['H-Alpha', 'Halpha', 'R', 'Red', 'Slot 8', ''])
        }

        def found(value):
            # The filter set's qs needs an API request (visibility); the method alone is tested here
            queryset = DataFileFilter().filter_image_filter(DataFile.objects.all(), 'image_filter', value)
            return {df.image_filter for df in queryset}

        self.assertEqual(found('h alpha'), {'H-Alpha', 'Halpha'})
        self.assertEqual(found('R'), {'R'})
        self.assertEqual(found('Slot 8'), {'Slot 8'})
        self.assertEqual(len(files), 6)
