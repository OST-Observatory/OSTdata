"""Plate solving: ASTAP backend (simulated astap_cli), solver fallback, error messages, retry pause."""
import math
import subprocess
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from obs_run.astap_solver import AstapError, AstapSolver, solution_from_header
from obs_run.management.commands.plate_solve_files import compare_solutions
from obs_run.models import DataFile, ObservationRun
from obs_run.plate_solving import (
    PlateSolver,
    PlateSolvingService,
    plate_solve_candidates,
    retry_due_filter,
    solve_and_update_datafile,
)
from users.models import User

NAXIS1, NAXIS2 = 64, 48
SCALE = 1.0 / 3600  # 1 arcsec per pixel


def _wcs_header(ra=83.82, dec=-5.39, rotation=30.0, scale_x=SCALE, scale_y=SCALE, skew=0.0):
    """TAN WCS with normal parity (east left when north is up), keywords as ASTAP writes them."""
    theta = math.radians(rotation)
    header = fits.Header()
    header['CTYPE1'], header['CTYPE2'] = 'RA---TAN', 'DEC--TAN'
    header['CUNIT1'], header['CUNIT2'] = 'deg', 'deg'
    header['CRPIX1'], header['CRPIX2'] = (NAXIS1 + 1) / 2, (NAXIS2 + 1) / 2
    header['CRVAL1'], header['CRVAL2'] = ra, dec
    header['CDELT1'], header['CDELT2'] = -scale_x, scale_y
    header['CROTA1'], header['CROTA2'] = rotation, rotation
    header['CD1_1'] = -scale_x * math.cos(theta)
    header['CD1_2'] = scale_y * math.sin(theta + math.radians(skew))
    header['CD2_1'] = scale_x * math.sin(theta)
    header['CD2_2'] = scale_y * math.cos(theta + math.radians(skew))
    header['PLTSOLVD'] = True
    return header


class FakeAstap:
    """Stands in for subprocess.run of astap_cli: writes .ini/.wcs to the -o base path like ASTAP."""

    def __init__(self, outcomes):
        # One outcome per call: a WCS header (solved) or an exit code (failed)
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        output = Path(cmd[cmd.index('-o') + 1])
        image = Path(cmd[cmd.index('-f') + 1])
        self.inputs = getattr(self, 'inputs', []) + [(image, image.is_symlink(), fits.getheader(image))]
        outcome = self.outcomes.pop(0) if self.outcomes else 1
        if isinstance(outcome, fits.Header):
            output.with_suffix('.wcs').write_bytes(outcome.tostring().encode('ascii'))
            output.with_suffix('.ini').write_text('PLTSOLVD=T\n')
            return SimpleNamespace(returncode=0, stdout='Solution found: 05: 35 19 -05° 23 24', stderr='')
        output.with_suffix('.ini').write_text('PLTSOLVD=F\n')
        return SimpleNamespace(returncode=outcome, stdout='No solution found!', stderr='')


@override_settings(PLATE_SOLVING_TIMEOUT_SECONDS=600, ASTAP_DATABASE='d50', ASTAP_DATABASE_DIR='/opt/astap')
class AstapSolverTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.hints = {'fov_x': NAXIS1 / 3600, 'fov_y': NAXIS2 / 3600, 'naxis1': NAXIS1, 'naxis2': NAXIS2}

    def _fits(self, data, **cards):
        path = self.tmp / 'frame.fits'
        hdu = fits.PrimaryHDU(data)
        hdu.header.update(cards)
        hdu.writeto(path, overwrite=True)
        return path

    def _solve(self, path, fake, nearby=True):
        solver = AstapSolver()
        with patch.object(AstapSolver, '_executable', return_value='/usr/bin/astap_cli'), \
                patch('obs_run.astap_solver.subprocess.run', side_effect=fake):
            if nearby:
                return solver.solve_nearby(str(path), 83.82, -5.39, 0.01, 5.0, hints=self.hints)
            return solver.solve(str(path), 0.1, 1.0, hints=self.hints)

    def test_raw_frame_is_linked_and_never_changed(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16), BAYERPAT='RGGB')
        before = path.read_bytes()
        fake = FakeAstap([_wcs_header()])

        result = self._solve(path, fake)

        cmd = fake.calls[0]
        self.assertEqual(cmd[:2], ['/usr/bin/astap_cli', '-f'])
        self.assertIn('-wcs', cmd)
        self.assertEqual(cmd[cmd.index('-r') + 1], '5')
        self.assertAlmostEqual(float(cmd[cmd.index('-fov') + 1]), NAXIS2 / 3600)
        self.assertAlmostEqual(float(cmd[cmd.index('-ra') + 1]), 83.82 / 15)
        self.assertAlmostEqual(float(cmd[cmd.index('-spd') + 1]), -5.39 + 90)
        self.assertEqual(cmd[cmd.index('-check') + 1], 'y')  # raw one-shot-colour frame
        self.assertEqual(cmd[cmd.index('-D') + 1], 'd50')
        self.assertEqual(cmd[cmd.index('-d') + 1], '/opt/astap')
        image, is_link, _ = fake.inputs[0]
        self.assertTrue(is_link)
        self.assertNotEqual(image.parent, path.parent)
        # Output only in the (removed) temporary directory, archive file untouched
        self.assertFalse(image.parent.exists())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ['frame.fits'])

        self.assertTrue(result['success'])
        self.assertAlmostEqual(result['ra'], 83.82, places=6)
        self.assertAlmostEqual(result['dec'], -5.39, places=6)
        self.assertAlmostEqual(result['pixScale'], 1.0, places=6)
        self.assertEqual(result['parity'], 'normal')
        self.assertAlmostEqual(result['fieldRadius'], math.hypot(NAXIS1, NAXIS2) / 2 / 3600, places=6)
        self.assertAlmostEqual(result['fits_crpix1'], (NAXIS1 + 1) / 2)

    def test_blind_search_without_coordinates(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))
        fake = FakeAstap([_wcs_header()])
        self._solve(path, fake, nearby=False)
        cmd = fake.calls[0]
        self.assertEqual(cmd[cmd.index('-r') + 1], '180')
        self.assertNotIn('-ra', cmd)
        self.assertNotIn('-check', cmd)

    def test_float_stack_gets_16_bit_copy_and_retries(self):
        rng = np.random.default_rng(1)
        data = rng.normal(0, 1, (NAXIS2, NAXIS1)).astype(np.float32)  # negative values, float
        data[10, 10] = 1e9  # masked pixel: must not set the stretch
        path = self._fits(data, CTYPE1='RA---TAN', CRVAL1=1.0)
        # linear: all star limits fail, asinh with the default star count solves
        fake = FakeAstap([1, 1, 1, _wcs_header()])

        result = self._solve(path, fake)

        self.assertTrue(result['success'])
        star_options = [c[c.index('-s') + 1] if '-s' in c else None for c in fake.calls]
        self.assertEqual(star_options, [None, '100', '50', None])
        names = [image.name for image, _, _ in fake.inputs]
        self.assertEqual(names, ['image_linear.fits'] * 3 + ['image_asinh.fits'])
        _, is_link, header = fake.inputs[0]
        self.assertFalse(is_link)
        self.assertEqual((header['BITPIX'], header.get('BZERO')), (16, 32768))
        self.assertNotIn('CTYPE1', header)  # old WCS removed

    def test_implausible_solutions_are_rejected(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))
        skewed = _wcs_header(skew=3.0)
        wrong_scale = _wcs_header(scale_x=2 * SCALE, scale_y=2 * SCALE)
        fake = FakeAstap([skewed, wrong_scale, 1])
        with self.assertRaises(AstapError) as ctx:
            self._solve(path, fake)
        message = str(ctx.exception)
        self.assertIn('axis rotations differ', message)
        self.assertIn('expected 1.000"/px', message)

    def test_missing_database_stops_at_once(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))
        fake = FakeAstap([32])
        with self.assertRaisesMessage(AstapError, 'no star database found'):
            self._solve(path, fake)
        self.assertEqual(len(fake.calls), 1)

    def test_timeout_is_reported(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))

        def hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs['timeout'])

        with self.assertRaisesMessage(AstapError, 'timeout after 120 s'):
            self._solve(path, hang)

    def test_text_style_wcs_file(self):
        header = _wcs_header()
        wcs_file = self.tmp / 'text.wcs'
        wcs_file.write_text(header.tostring(sep='\n'))
        from obs_run.astap_solver import _read_wcs_header

        result = solution_from_header(_read_wcs_header(wcs_file), NAXIS1, NAXIS2)
        self.assertAlmostEqual(result['ra'], 83.82, places=6)

    def test_mirrored_solution_has_flipped_parity(self):
        header = _wcs_header()
        header['CD1_1'] = -header['CD1_1']
        header['CD2_1'] = -header['CD2_1']
        self.assertEqual(solution_from_header(header, NAXIS1, NAXIS2)['parity'], 'flipped')


class FailingSolver(PlateSolver):
    def __init__(self, name, message):
        self.name, self.message = name, message

    def get_name(self):
        return self.name

    def is_available(self):
        return True

    def solve(self, image_path, min_radius, max_radius, hints=None):
        raise RuntimeError(self.message)

    def solve_nearby(self, image_path, ra_deg, dec_deg, field_radius, search_radius, hints=None):
        raise RuntimeError(f'{self.message} (nearby)')


class SolveAndUpdateTest(TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / 'frame.fits'
        fits.PrimaryHDU(np.zeros((NAXIS2, NAXIS1), dtype=np.uint16)).writeto(path)
        run = ObservationRun.objects.create(name='2026-11-02')
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(path), file_type='FITS', exposure_type='LI',
            naxis1=NAXIS1, naxis2=NAXIS2, ra=83.82, dec=-5.39,
        )

    def test_reasons_of_all_solvers_are_stored(self):
        service = PlateSolvingService(solvers=[
            FailingSolver('astap', 'no solution found'), FailingSolver('watney', 'Watney failed with exit code 1'),
        ])
        result = solve_and_update_datafile(self.datafile, service=service)
        self.assertFalse(result['success'])
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.plate_solve_error, (
            'astap nearby: no solution found (nearby); astap blind: no solution found; '
            'watney nearby: Watney failed with exit code 1 (nearby); watney blind: Watney failed with exit code 1'
        ))
        self.assertEqual(self.datafile.plate_solve_attempts, 1)
        solve_and_update_datafile(self.datafile, service=service)
        self.assertEqual(self.datafile.plate_solve_attempts, 2)

    def test_next_solver_is_used_and_attempts_reset(self):
        self.datafile.plate_solve_attempts = 3
        solution = solution_from_header(_wcs_header(), NAXIS1, NAXIS2)

        class Solved(FailingSolver):
            def solve_nearby(self, *args, **kwargs):
                return dict(solution)

        service = PlateSolvingService(solvers=[FailingSolver('astap', 'no solution found'), Solved('watney', '')])
        with patch('obs_run.sky_view.prerender_sky_image'):
            result = solve_and_update_datafile(self.datafile, service=service)
        self.assertEqual((result['success'], result['tool']), (True, 'watney'))
        self.datafile.refresh_from_db()
        self.assertEqual((self.datafile.plate_solve_attempts, self.datafile.plate_solve_tool), (0, 'watney'))
        self.assertAlmostEqual(self.datafile.wcs_crval1, 83.82)


@override_settings(PLATE_SOLVING_RETRY_HOURS=6, PLATE_SOLVING_RETRY_MAX_DAYS=30)
class RetryPauseTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-11-03')
        self.now = timezone.now()

    def _file(self, name, attempts=0, hours_ago=None):
        return DataFile.objects.create(
            observation_run=self.run, datafile=f'/data/{name}.fits', file_type='FITS', exposure_type='LI',
            plate_solve_attempts=attempts,
            plate_solve_attempted_at=None if hours_ago is None else self.now - timedelta(hours=hours_ago),
        )

    def test_pause_doubles_with_every_failure(self):
        due = {
            self._file('new').pk: True,
            self._file('legacy_recent', attempts=0, hours_ago=1).pk: False,  # attempted before the counter
            self._file('first_fail_old', attempts=1, hours_ago=7).pk: True,
            self._file('third_fail_recent', attempts=3, hours_ago=20).pk: False,  # pause 24 h
            self._file('third_fail_old', attempts=3, hours_ago=25).pk: True,
            self._file('many_fails', attempts=20, hours_ago=24 * 29).pk: False,  # capped at 30 days
            self._file('many_fails_old', attempts=20, hours_ago=24 * 31).pk: True,
        }
        found = set(DataFile.objects.filter(retry_due_filter(self.now)).values_list('pk', flat=True))
        self.assertEqual(found, {pk for pk, is_due in due.items() if is_due})

    def test_candidates_new_files_first(self):
        old = self._file('old_fail', attempts=1, hours_ago=100)
        new = self._file('new')
        self.assertEqual(list(plate_solve_candidates().values_list('pk', flat=True)), [new.pk, old.pk])
        recent = self._file('recent_fail', attempts=1, hours_ago=1)
        self.assertNotIn(recent.pk, plate_solve_candidates().values_list('pk', flat=True))
        self.assertIn(recent.pk, plate_solve_candidates(ignore_backoff=True).values_list('pk', flat=True))


class CompareSolutionsTest(TestCase):
    def test_same_and_mirrored_solution(self):
        wcs = WCS(_wcs_header())
        center, corner, ratio = compare_solutions(wcs, WCS(_wcs_header()), NAXIS1, NAXIS2)
        self.assertLess(max(center, corner), 1e-6)
        self.assertAlmostEqual(ratio, 1.0)
        mirrored = _wcs_header()
        mirrored['CD1_1'] = -mirrored['CD1_1']
        mirrored['CD2_1'] = -mirrored['CD2_1']
        center, corner, _ = compare_solutions(wcs, WCS(mirrored), NAXIS1, NAXIS2)
        self.assertLess(center, 1e-6)
        self.assertGreater(corner, 30)  # same center, corners far apart: flipped solution

    @override_settings(PLATE_SOLVING_TOOLS=['astap'])
    def test_command_without_astap(self):
        out = StringIO()
        with patch.object(AstapSolver, '_executable', return_value=None):
            call_command('plate_solve_files', '--compare', stdout=out)
        self.assertIn('No files to process', out.getvalue())


class SolverStatusApiTest(APITestCase):
    def test_stats_list_the_solvers(self):
        admin = User.objects.create_superuser(username='admin', password='pw', email='a@example.org')
        self.client.force_authenticate(admin)
        with patch.object(AstapSolver, '_executable', return_value=None), \
                override_settings(PLATE_SOLVING_TOOLS=['astap', 'watney'], WATNEY_SOLVE_PATH='/nonexistent/watney'):
            response = self.client.get('/api/admin/datafiles/plate-solving/stats/')
        self.assertEqual(response.status_code, 200)
        solvers = response.json()['solvers']
        self.assertEqual([s['name'] for s in solvers], ['astap', 'watney'])
        self.assertFalse(any(s['available'] for s in solvers))
        self.assertIn('astap_cli not found', solvers[0]['details'])
        self.assertEqual(response.json()['solved_by_tool'], {})
