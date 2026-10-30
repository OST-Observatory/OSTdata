"""Preview cache: status, optional cleanup, last-use tracking, sky image rendered after plate solving."""
import os
import tempfile
import time
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from astropy.io import fits
from django.core.management import call_command
from django.test import TestCase, override_settings

from obs_run.models import DataFile, ObservationRun
from obs_run.plate_solving import solve_and_update_datafile
from obs_run.preview_cache import cache_status, cleanup_cache
from obs_run.sky_view import _cache_path, get_sky_jpeg

OLD = time.time() - 200 * 86400


def _write(directory, name, size=100, mtime=None):
    path = Path(directory) / name
    path.write_bytes(b'x' * size)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


class PreviewCacheTest(TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp()
        override = override_settings(SER_THUMBNAIL_CACHE_DIR=self.cache, PREVIEW_CACHE_MAX_AGE_DAYS=90)
        override.enable()
        self.addCleanup(override.disable)
        run = ObservationRun.objects.create(name='2026-11-01', is_public=True)
        self.df = DataFile.objects.create(observation_run=run, datafile='/tmp/a.fits', file_type='FITS',
                                          content_hash='h1')
        pk = self.df.pk
        self.files = {
            'keep_sky': _write(self.cache, f'df{pk}_h1_sky2048_v2.jpg', 300),
            'keep_thumb': _write(self.cache, f'df{pk}_h1_w512.png', 200),
            'unused': _write(self.cache, f'df{pk}_h1_sky1024_v2.jpg', 50, mtime=OLD),
            'outdated_format': _write(self.cache, f'df{pk}_h1_sky2048.jpg', 40),
            'file_changed': _write(self.cache, f'df{pk}_h0_w512.png', 30),
            'file_deleted': _write(self.cache, f'df{pk + 999}_h1_sky2048_v2.jpg', 20),
            'other': _write(self.cache, 'README.txt', 10),
        }

    def test_status(self):
        status = cache_status()
        self.assertEqual(status['kinds']['sky']['files'], 4)
        self.assertEqual(status['kinds']['sky']['bytes'], 300 + 50 + 40 + 20)
        self.assertEqual(status['kinds']['thumbnail']['files'], 2)
        self.assertEqual(status['kinds']['other']['files'], 1)
        self.assertEqual(status['total_bytes'], 650)
        self.assertIsNotNone(status['free_bytes'])

    def test_cleanup(self):
        dry = cleanup_cache(dry_run=True)
        self.assertEqual(dry['removed_files'], 4)
        self.assertTrue(all(path.exists() for path in self.files.values()))

        summary = cleanup_cache()
        self.assertEqual(summary['reasons'], {'unused': 1, 'file_deleted': 1, 'file_changed': 1, 'outdated_format': 1})
        self.assertEqual(summary['removed_bytes'], 50 + 20 + 30 + 40)
        remaining = {name for name, path in self.files.items() if path.exists()}
        self.assertEqual(remaining, {'keep_sky', 'keep_thumb', 'other'})

    def test_command(self):
        out = StringIO()
        call_command('cleanup_preview_cache', '--max-age-days', '0', '--dry-run', stdout=out)
        # max age 0: also the recently used files count as unused
        self.assertIn('would remove 6 files', out.getvalue())


class SkyImageLifecycleTest(TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp()
        override = override_settings(SER_THUMBNAIL_CACHE_DIR=self.cache, SKY_VIEW_PRERENDER=True)
        override.enable()
        self.addCleanup(override.disable)
        self.path = Path(tempfile.mkdtemp()) / 'field.fits'
        fits.PrimaryHDU(np.random.default_rng(3).normal(1000, 20, (300, 400)).astype(np.float32)).writeto(self.path)
        run = ObservationRun.objects.create(name='2026-11-02', is_public=True)
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(self.path), file_type='FITS', naxis1=400, naxis2=300,
            content_hash='solve-test',
        )

    def test_new_plate_solution_renders_the_sky_image(self):
        service = MagicMock()
        service.solvers = [MagicMock(get_supported_formats=lambda: ['fits'])]
        service.calculate_radius_from_fov.return_value = (0.1, 1.0)
        service.solve.return_value = {
            'success': True, 'tool': 'test', 'ra': 10.0, 'dec': 20.0,
            'fits_crval1': 10.0, 'fits_crval2': 20.0, 'fits_crpix1': 200.5, 'fits_crpix2': 150.5,
            'fits_cd1_1': -1 / 3600, 'fits_cd1_2': 0.0, 'fits_cd2_1': 0.0, 'fits_cd2_2': 1 / 3600,
        }
        cache_file = _cache_path(self.datafile, 2048)
        self.assertFalse(cache_file.exists())
        self.assertTrue(solve_and_update_datafile(self.datafile, service=service)['success'])
        self.assertTrue(cache_file.exists())

    def test_cache_hit_marks_the_last_use(self):
        get_sky_jpeg(self.datafile, self.path)
        cache_file = _cache_path(self.datafile, 2048)
        # Older than the last use, but still newer than the source file: valid and touched on reading
        os.utime(self.path, (OLD - 10, OLD - 10))
        os.utime(cache_file, (OLD, OLD))
        get_sky_jpeg(self.datafile, self.path)
        self.assertGreater(cache_file.stat().st_mtime, time.time() - 60)
