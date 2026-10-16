"""Image quality flags: assessment, backfill command, filter and exclusion from the training export."""
import tempfile
from io import StringIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APITestCase

from obs_run import image_quality
from obs_run.models import DataFile, ObservationRun
from obs_run.training_export import collect_records


def _write(path, data, header=None):
    hdu = fits.PrimaryHDU(data)
    for key, value in (header or {}).items():
        hdu.header[key] = value
    hdu.writeto(path, overwrite=True)
    return str(path)


class AssessTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.rng = np.random.default_rng(0)

    def _frame(self, name, level, header=None, dtype=np.uint16):
        data = np.clip(self.rng.normal(level, 20, (200, 300)), 0, 65535).astype(dtype)
        return _write(self.tmp / name, data, header)

    def _check(self, path, file_type='FITS'):
        return image_quality.check_datafile(DataFile(datafile=path, file_type=file_type))

    def test_flags(self):
        self.assertEqual(self._check(self._frame('dark.fits', 1000))[0], image_quality.OK)
        flat = self._check(self._frame('flat.fits', 30000))
        self.assertEqual(flat[0], image_quality.OK)
        self.assertAlmostEqual(flat[2], 30000 / 65535, places=2)
        saturated = self._check(self._frame('nova.fits', 65535))
        self.assertEqual(saturated[0], image_quality.OVEREXPOSED)
        self.assertGreater(saturated[1], 0.4)
        constant = _write(self.tmp / 'constant.fits', np.full((50, 50), 7, dtype=np.uint16))
        self.assertEqual(self._check(constant)[0], image_quality.EMPTY)
        # Completely saturated frames are constant too, but over-exposed
        full = _write(self.tmp / 'full.fits', np.full((50, 50), 65535, dtype=np.uint16))
        self.assertEqual(self._check(full), (image_quality.OVEREXPOSED, 1.0, 1.0))

    def test_saturation_from_header(self):
        self.assertEqual(self._check(self._frame('a.fits', 45000))[0], image_quality.OK)
        self.assertEqual(self._check(self._frame('b.fits', 45000, {'SATURATE': 44000}))[0], image_quality.OVEREXPOSED)

    def test_float_data_without_level(self):
        path = _write(self.tmp / 'float.fits', self.rng.normal(0, 1, (50, 50)).astype(np.float32))
        self.assertEqual(self._check(path), (image_quality.OK, None, None))

    def test_unreadable_and_unchecked(self):
        bad = self.tmp / 'bad.fits'
        bad.write_bytes(b'garbage')
        self.assertEqual(self._check(str(bad))[0], image_quality.UNREADABLE)
        self.assertEqual(self._check(str(bad), 'CR2')[0], image_quality.NOT_CHECKED)


class QualityCommandAndFiltersTest(APITestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        rng = np.random.default_rng(1)
        run = ObservationRun.objects.create(name='night', is_public=True)
        self.good = DataFile.objects.create(
            observation_run=run, file_type='FITS', exposure_type='LI', exposure_type_ml='LI',
            datafile=_write(self.tmp / 'good.fits', np.clip(rng.normal(1000, 20, (80, 80)), 0, None).astype(np.uint16)),
        )
        self.bad = DataFile.objects.create(
            observation_run=run, file_type='FITS', exposure_type='LI', exposure_type_ml='LI',
            datafile=_write(self.tmp / 'nova.fits', np.full((80, 80), 65535, dtype=np.uint16)
                            - rng.integers(0, 2, (80, 80)).astype(np.uint16)),
        )

    def _flags(self):
        return dict(DataFile.objects.values_list('pk', 'quality_flag'))

    def test_command_dry_run_then_save(self):
        out = StringIO()
        call_command('compute_image_quality', '--dry-run', stdout=out)
        self.assertIn('nothing saved', out.getvalue())
        self.assertEqual(set(self._flags().values()), {image_quality.NOT_CHECKED})

        call_command('compute_image_quality', stdout=StringIO())
        self.assertEqual(self._flags(), {self.good.pk: image_quality.OK, self.bad.pk: image_quality.OVEREXPOSED})

    def test_recheck_by_flag(self):
        DataFile.objects.update(quality_flag=image_quality.EMPTY)
        DataFile.objects.filter(pk=self.good.pk).update(quality_flag=image_quality.OK)
        call_command('compute_image_quality', '--flag', 'EM', stdout=StringIO())
        # only the file flagged EM was rechecked
        self.assertEqual(self._flags(), {self.good.pk: image_quality.OK, self.bad.pk: image_quality.OVEREXPOSED})

    def test_manual_flag_is_kept(self):
        DataFile.objects.filter(pk=self.bad.pk).update(quality_flag=image_quality.OK, quality_flag_override=True)
        call_command('compute_image_quality', '--recheck', stdout=StringIO())
        self.assertEqual(self._flags()[self.bad.pk], image_quality.OK)

    def test_filter_and_training_export(self):
        call_command('compute_image_quality', stdout=StringIO())
        response = self.client.get('/api/runs/datafiles/', {'quality_flag': ['OE', 'EM', 'UR']})
        self.assertEqual([row['pk'] for row in response.json()['results']], [self.bad.pk])
        self.assertEqual(response.json()['results'][0]['quality_flag'], 'OE')

        records = collect_records(['FITS'], self.tmp)
        self.assertEqual([r['pk'] for r in records], [self.good.pk])
