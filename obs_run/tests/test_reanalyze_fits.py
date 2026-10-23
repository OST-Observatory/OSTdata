"""Header re-analysis: linked targets, saves only on change, honest dry run of reanalyze_fits."""
from contextlib import contextmanager
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from objects.models import Object
from obs_run.analyze_fits_header import analyze_fits
from obs_run.models import DataFile, ObservationRun

HEADER = {'objectname': 'M31_field', 'naxis1': 100, 'naxis2': 100, 'exptime': 60.0}


@contextmanager
def fits_header(header):
    with patch.object(DataFile, 'get_fits_header', return_value={}), \
            patch('obs_run.analyze_fits_header.extract_fits_header_info', return_value=header):
        yield


class AnalyzeFitsChangesTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-10-03', is_public=True)
        self.datafile = DataFile.objects.create(
            observation_run=self.run, datafile='/tmp/m31.fits', file_type='FITS', exposure_type='LI',
        )

    def test_linked_file_keeps_object_as_target(self):
        obj = Object.objects.create(name='M 31', is_public=True, object_type='GA')
        obj.datafiles.add(self.datafile)
        DataFile.objects.filter(pk=self.datafile.pk).update(main_target='M 31')
        self.datafile.refresh_from_db()
        with fits_header(HEADER):
            analyze_fits(self.datafile)
        self.datafile.refresh_from_db()
        self.assertEqual((self.datafile.main_target, self.datafile.header_target_name), ('M 31', 'M31_field'))

    def test_unlinked_file_gets_header_target(self):
        with fits_header(HEADER):
            analyze_fits(self.datafile)
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.main_target, 'M31_field')

    def test_unchanged_file_is_not_saved_again(self):
        with fits_header(HEADER):
            self.assertIn('exptime', analyze_fits(self.datafile))
            history_count = self.datafile.history.count()
            self.datafile.refresh_from_db()
            self.assertEqual(analyze_fits(self.datafile), {})
        self.assertEqual(self.datafile.history.count(), history_count)

    def test_save_false_reports_without_writing(self):
        with fits_header({**HEADER, 'exptime': 120.0}):
            changes = analyze_fits(self.datafile, save=False)
        self.assertEqual(changes['exptime'][1], 120.0)
        self.assertEqual(DataFile.objects.get(pk=self.datafile.pk).exptime, -1)


class ReanalyzeFitsCommandTest(TestCase):
    def test_dry_run_reports_header_changes_per_field(self):
        run = ObservationRun.objects.create(name='2026-10-04', is_public=True)
        datafile = DataFile.objects.create(observation_run=run, datafile='/tmp/a.fits', file_type='FITS')
        out = StringIO()
        with fits_header(HEADER):
            call_command('reanalyze_fits', '--dry-run', '--skip-evaluation', stdout=out)
        output = out.getvalue()
        self.assertIn('Header analysis: 1 files would change, 0 unchanged', output)
        self.assertIn('  exptime: 1', output)
        self.assertEqual(DataFile.objects.get(pk=datafile.pk).exptime, -1)
