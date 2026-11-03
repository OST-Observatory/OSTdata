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
from obs_run.models import DataFile, ObservationRun, PlateSolveFailure
from obs_run.plate_solving import (
    PlateSolver,
    PlateSolvingService,
    SolverSetupError,
    plate_solve_candidates,
    reset_plate_solve_failures,
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

    def test_database_directory_is_found_automatically(self):
        # astap_cli only looks next to its executable: the found directory must be passed with -d
        empty, databases = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        (databases / 'd80_0101.1476').write_bytes(b'')
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))
        with override_settings(ASTAP_DATABASE_DIR='', ASTAP_DATABASE=''), \
                patch.object(AstapSolver, '_database_dirs', return_value=[empty, databases]):
            fake = FakeAstap([_wcs_header()])
            self._solve(path, fake)
            self.assertEqual(fake.calls[0][fake.calls[0].index('-d') + 1], str(databases))
            self.assertNotIn('-D', fake.calls[0])
            self.assertEqual(AstapSolver().installed_databases(), ['d80'])

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

    def test_missing_database_is_a_setup_error(self):
        path = self._fits(np.full((NAXIS2, NAXIS1), 1000, dtype=np.uint16))
        fake = FakeAstap([32])
        with self.assertRaisesMessage(SolverSetupError, 'no star database found'):
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
    def __init__(self, name, message, error=RuntimeError):
        self.name, self.message, self.error = name, message, error
        self.calls = 0

    def get_name(self):
        return self.name

    def is_available(self):
        return True

    def solve(self, image_path, min_radius, max_radius, hints=None):
        self.calls += 1
        raise self.error(self.message)

    def solve_nearby(self, image_path, ra_deg, dec_deg, field_radius, search_radius, hints=None):
        self.calls += 1
        raise self.error(f'{self.message} (nearby)')


class SolveAndUpdateTest(TestCase):
    def setUp(self):
        path = Path(tempfile.mkdtemp()) / 'frame.fits'
        fits.PrimaryHDU(np.zeros((NAXIS2, NAXIS1), dtype=np.uint16)).writeto(path)
        run = ObservationRun.objects.create(name='2026-11-02')
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(path), file_type='FITS', exposure_type='LI',
            naxis1=NAXIS1, naxis2=NAXIS2, ra=83.82, dec=-5.39,
        )

    def _failed_tools(self):
        return dict(self.datafile.plate_solve_failures.values_list('tool', 'error'))

    def test_each_solver_gets_one_chance(self):
        astap = FailingSolver('astap', 'no solution found')
        watney = FailingSolver('watney', 'Watney failed with exit code 1')
        service = PlateSolvingService(solvers=[astap, watney])
        result = solve_and_update_datafile(self.datafile, service=service)
        self.assertFalse(result['success'])
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.plate_solve_error, (
            'astap nearby: no solution found (nearby); astap blind: no solution found; '
            'watney nearby: Watney failed with exit code 1 (nearby); watney blind: Watney failed with exit code 1'
        ))
        self.assertEqual(self._failed_tools(), {
            'astap': 'astap nearby: no solution found (nearby); astap blind: no solution found',
            'watney': 'watney nearby: Watney failed with exit code 1 (nearby); '
                      'watney blind: Watney failed with exit code 1',
        })
        self.assertEqual((astap.calls, watney.calls), (2, 2))

        # Second run: no solver is tried again
        result = solve_and_update_datafile(self.datafile, service=service)
        self.assertEqual(result['error'], 'Already failed with all available solvers (astap, watney)')
        self.assertEqual((astap.calls, watney.calls), (2, 2))

        # Explicit retry (manual trigger) tries them all
        solve_and_update_datafile(self.datafile, service=service, retry_failed=True)
        self.assertEqual((astap.calls, watney.calls), (4, 4))

    def test_only_the_new_solver_is_tried(self):
        astap = FailingSolver('astap', 'no solution found')
        solve_and_update_datafile(self.datafile, service=PlateSolvingService(solvers=[astap]))
        solution = solution_from_header(_wcs_header(), NAXIS1, NAXIS2)

        class Solved(FailingSolver):
            def solve_nearby(self, *args, **kwargs):
                self.calls += 1
                return dict(solution)

        watney = Solved('watney', '')
        service = PlateSolvingService(solvers=[astap, watney])
        with patch('obs_run.sky_view.prerender_sky_image'):
            result = solve_and_update_datafile(self.datafile, service=service)
        self.assertEqual((result['success'], result['tool']), (True, 'watney'))
        self.assertEqual((astap.calls, watney.calls), (2, 1))  # astap only in the first run
        self.datafile.refresh_from_db()
        self.assertEqual(self.datafile.plate_solve_tool, 'watney')
        self.assertAlmostEqual(self.datafile.wcs_crval1, 83.82)

    def test_setup_problems_are_no_failures_of_the_file(self):
        broken = FailingSolver('astap', 'no star database found', error=SolverSetupError)
        solve_and_update_datafile(self.datafile, service=PlateSolvingService(solvers=[broken]))
        self.assertEqual(self._failed_tools(), {})
        self.datafile.refresh_from_db()
        self.assertIn('no star database found', self.datafile.plate_solve_error)
        self.assertEqual(broken.calls, 1)  # blind search skipped after the setup error


class CandidatesTest(TestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2026-11-03')
        self.now = timezone.now()

    def _file(self, name, failed=(), hours_ago=None):
        datafile = DataFile.objects.create(
            observation_run=self.run, datafile=f'/data/{name}.fits', file_type='FITS', exposure_type='LI',
            plate_solve_attempted_at=None if hours_ago is None else self.now - timedelta(hours=hours_ago),
        )
        for tool in failed:
            PlateSolveFailure.objects.create(datafile=datafile, tool=tool, failed_at=self.now)
        return datafile

    def _pks(self, **kwargs):
        return list(plate_solve_candidates(**kwargs).values_list('pk', flat=True))

    def test_files_with_an_untried_solver(self):
        astap_failed = self._file('astap_failed', failed=['astap'], hours_ago=2)
        new = self._file('new')
        both_failed = self._file('both_failed', failed=['astap', 'watney'], hours_ago=1)
        old_watney = self._file('old_watney_failure', failed=['watney'], hours_ago=5)

        # New files first, then the longest waiting
        self.assertEqual(self._pks(tools=['astap', 'watney']), [new.pk, old_watney.pk, astap_failed.pk])
        self.assertEqual(self._pks(tools=['astap']), [new.pk, old_watney.pk])
        self.assertIn(both_failed.pk, self._pks(tools=['astap'], retry_failed=True))
        self.assertEqual(self._pks(tools=[]), [])

    def test_reset_per_solver(self):
        datafile = self._file('both_failed', failed=['astap', 'watney'], hours_ago=1)
        self.assertEqual(reset_plate_solve_failures('astap'), 1)
        self.assertEqual(list(datafile.plate_solve_failures.values_list('tool', flat=True)), ['watney'])
        self.assertEqual(self._pks(tools=['astap', 'watney']), [datafile.pk])


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

    def test_reset_failures_endpoint(self):
        admin = User.objects.create_superuser(username='admin2', password='pw', email='b@example.org')
        self.client.force_authenticate(admin)
        run = ObservationRun.objects.create(name='2026-11-05')
        datafile = DataFile.objects.create(observation_run=run, datafile='/data/x.fits', file_type='FITS',
                                           exposure_type='LI')
        for tool in ('astap', 'watney'):
            PlateSolveFailure.objects.create(datafile=datafile, tool=tool, failed_at=timezone.now())
        with patch.object(AstapSolver, 'describe', return_value={'name': 'astap', 'available': True}), \
                override_settings(PLATE_SOLVING_TOOLS=['astap']):
            stats = self.client.get('/api/admin/datafiles/plate-solving/stats/').json()
        self.assertEqual(stats['failed_by_tool'], {'astap': 1, 'watney': 1})
        self.assertEqual(stats['exhausted'], 1)

        response = self.client.post('/api/admin/datafiles/plate-solving/reset-failures/', {'tool': 'astap'},
                                    format='json')
        self.assertEqual(response.json(), {'tool': 'astap', 'reset': 1})
        self.assertEqual(list(PlateSolveFailure.objects.values_list('tool', flat=True)), ['watney'])
        self.assertEqual(self.client.post('/api/admin/datafiles/plate-solving/reset-failures/', {},
                                          format='json').status_code, 400)


class BackgroundTriggerApiTest(APITestCase):
    def setUp(self):
        admin = User.objects.create_superuser(username='admin', password='pw', email='a@example.org')
        self.client.force_authenticate(admin)
        path = Path(tempfile.mkdtemp()) / 'frame.fits'
        fits.PrimaryHDU(np.zeros((NAXIS2, NAXIS1), dtype=np.uint16)).writeto(path)
        run = ObservationRun.objects.create(name='2026-11-04')
        self.datafile = DataFile.objects.create(
            observation_run=run, datafile=str(path), file_type='FITS', exposure_type='LI',
            naxis1=NAXIS1, naxis2=NAXIS2,
        )

    def _status(self, job):
        return self.client.get('/api/admin/datafiles/plate-solving/trigger/status/', {
            'ids': ','.join(map(str, job['file_ids'])), 'since': job['queued_at'],
        }).json()

    def test_trigger_queues_a_task_and_status_reports_the_result(self):
        from obs_run.tasks import plate_solve_selected_files

        solvers = [FailingSolver('astap', 'no solution found')]
        # A real id: a MagicMock in the JSON response makes DRF's encoder loop and fill the memory
        queued = SimpleNamespace(id='task-1')
        with patch.object(PlateSolvingService, '_create_solvers_from_settings', return_value=solvers), \
                patch.object(plate_solve_selected_files, 'delay', return_value=queued) as delay:
            response = self.client.post('/api/admin/datafiles/plate-solving/trigger/',
                                        {'file_ids': [self.datafile.pk]}, format='json')
            self.assertEqual(response.status_code, 202)
            job = response.json()
            self.assertEqual(job['task_id'], 'task-1')
            delay.assert_called_once_with([self.datafile.pk])
            # Queued, not solved yet: the request returns at once
            self.assertEqual(self._status(job)['done'], False)

            plate_solve_selected_files([self.datafile.pk])  # what the Celery worker does

        status = self._status(job)
        self.assertTrue(status['done'])
        self.assertEqual(status['files'], [{
            'file_id': self.datafile.pk, 'done': True, 'success': False, 'tool': None,
            'error': 'astap blind: no solution found',  # no header coordinates: blind search only
        }])

    def test_no_solver_available(self):
        with patch.object(PlateSolvingService, '_create_solvers_from_settings', return_value=[]):
            response = self.client.post('/api/admin/datafiles/plate-solving/trigger/',
                                        {'file_ids': [self.datafile.pk]}, format='json')
        self.assertEqual(response.status_code, 503)

    def test_status_requires_ids_and_time(self):
        response = self.client.get('/api/admin/datafiles/plate-solving/trigger/status/', {'ids': '1'})
        self.assertEqual(response.status_code, 400)
