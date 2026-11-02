"""Completing the padding of the last FITS block of files flagged by the file integrity check."""
import os
import tempfile
import warnings
from io import StringIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from django.core.management import call_command
from django.test import TestCase

from obs_run.file_check import update_file_issues
from obs_run.fits_padding import fix_fits_padding, missing_padding
from obs_run.models import DataFile, ObservationRun
from utilities import compute_file_hash

# 217 x 202 int16: data end at 2880 + 87668 bytes, padded file 92160 bytes
SHAPE = (217, 202)
DATA_END = 2880 + 87668


class FitsPaddingTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run = ObservationRun.objects.create(name='2026-11-01')
        self.data = np.arange(SHAPE[0] * SHAPE[1], dtype=np.int16).reshape(SHAPE)

    def _datafile(self, name, cut):
        path = self.tmp / name
        fits.PrimaryHDU(self.data).writeto(path)
        path.write_bytes(path.read_bytes()[:-cut])
        datafile = DataFile.objects.create(
            observation_run=self.run, datafile=str(path), file_type='FITS',
            file_size=path.stat().st_size, content_hash=compute_file_hash(path),
        )
        update_file_issues(datafile)
        return datafile, path

    def test_unpadded_file_is_completed(self):
        datafile, path = self._datafile('unpadded.fits', cut=92160 - DATA_END)
        os.utime(path, (1_700_000_000, 1_700_000_000))
        self.assertEqual(datafile.file_issue_level, 'warning')

        results = fix_fits_padding()

        self.assertEqual([(r['status'], r['missing']) for r in results], [('padded', 92160 - DATA_END)])
        self.assertEqual(path.stat().st_size, 92160)
        self.assertEqual(path.stat().st_mtime, 1_700_000_000)
        with warnings.catch_warnings():
            warnings.simplefilter('error')  # no "File may have been truncated" any more
            with fits.open(path) as hdul:
                np.testing.assert_array_equal(hdul[0].data, self.data)
        datafile.refresh_from_db()
        self.assertEqual((datafile.file_size, datafile.content_hash), (92160, compute_file_hash(path)))
        self.assertEqual((datafile.file_issues, datafile.file_issue_level), ([], ''))
        self.assertFalse(list(self.tmp.glob('*.filepart')))
        self.assertEqual(datafile.history.count(), 1)  # creation only: no history entry for the fix

    def test_dry_run_changes_nothing(self):
        datafile, path = self._datafile('unpadded.fits', cut=100)
        before = path.read_bytes()
        out = StringIO()
        call_command('fix_fits_padding', '--dry-run', stdout=out)
        self.assertIn('would pad (100 bytes)', out.getvalue())
        self.assertEqual(path.read_bytes(), before)
        datafile.refresh_from_db()
        self.assertEqual(datafile.file_issue_level, 'warning')

    def test_truncated_data_are_not_padded(self):
        path = self.tmp / 'cut.fits'
        fits.PrimaryHDU(self.data).writeto(path)
        path.write_bytes(path.read_bytes()[:DATA_END - 500])
        self.assertEqual(missing_padding(path), (0, b''))

    def test_ascii_table_is_padded_with_spaces(self):
        path = self.tmp / 'table.fits'
        table = fits.TableHDU.from_columns([fits.Column(name='a', format='I5', array=np.arange(7))])
        fits.HDUList([fits.PrimaryHDU(), table]).writeto(path)
        content = path.read_bytes().rstrip(b' ')
        path.write_bytes(content)
        self.assertEqual(missing_padding(path), (-(-len(content) // 2880) * 2880 - len(content), b' '))

    def test_command_without_flagged_files(self):
        out = StringIO()
        call_command('fix_fits_padding', stdout=out)
        self.assertIn('No files with missing FITS padding', out.getvalue())
