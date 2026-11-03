"""Duplicate data file entries (same path): merging them and the unique path constraint."""
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from objects.models import Object
from obs_run.models import DataFile, ObservationRun, PlateSolveFailure


class UniquePathTest(TestCase):
    def test_paths_are_unique(self):
        run = ObservationRun.objects.create(name='2026-11-01')
        DataFile.objects.create(observation_run=run, datafile='/data/2026-11-01/a.fits', file_type='FITS')
        with self.assertRaises(IntegrityError):
            DataFile.objects.create(observation_run=run, datafile='/data/2026-11-01/a.fits', file_type='FITS')


class MergeDuplicateDatafilesTest(TransactionTestCase):
    """Runs on the schema before the unique constraint (0023), where duplicates could still exist."""

    BEFORE = [('obs_run', '0023_plate_solve_failure')]
    AFTER = [('obs_run', '0024_datafile_unique_path')]
    PATH = '/data/2026-10-24/Light/M31_001.fits'

    def setUp(self):
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.BEFORE)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _duplicates(self):
        run = ObservationRun.objects.create(name='2026-10-24')
        first = DataFile.objects.create(observation_run=run, datafile=self.PATH, file_type='FITS')
        # The later entry has the plate solution and a manual classification
        second = DataFile.objects.create(
            observation_run=run, datafile=self.PATH, file_type='FITS', plate_solved=True,
            exposure_type_user='LI',
        )
        first.exposure_type = 'DA'
        first.exposure_type_override = True
        first.save()
        galaxy = Object.objects.create(name='M 31', is_public=True, object_type='GA')
        galaxy.datafiles.add(first)
        PlateSolveFailure.objects.create(datafile=first, tool='watney', failed_at=timezone.now())
        return first, second, galaxy

    def test_merge_keeps_one_entry_with_all_links(self):
        first, second, galaxy = self._duplicates()
        out = StringIO()
        call_command('merge_duplicate_datafiles', stdout=out)
        self.assertIn(f'keep #{second.pk}', out.getvalue())
        self.assertIn('exposure_type_override from', out.getvalue())
        self.assertEqual(DataFile.objects.filter(datafile=self.PATH).count(), 2)  # dry run

        call_command('merge_duplicate_datafiles', '--apply', stdout=StringIO())
        kept = DataFile.objects.get(datafile=self.PATH)
        self.assertEqual(kept.pk, second.pk)  # plate solved entry wins
        self.assertIn(galaxy, kept.object_set.all())
        self.assertEqual(list(kept.plate_solve_failures.values_list('tool', flat=True)), ['watney'])
        self.assertEqual((kept.exposure_type, kept.exposure_type_override, kept.exposure_type_user),
                         ('DA', True, 'LI'))

        # Now the unique constraint can be added
        MigrationExecutor(connection).migrate(self.AFTER)

    def test_migration_refuses_duplicates_until_merged(self):
        first, _, _ = self._duplicates()
        with self.assertRaisesMessage(RuntimeError, 'merge_duplicate_datafiles --apply'):
            MigrationExecutor(connection).migrate(self.AFTER)
        first.delete()  # what merge_duplicate_datafiles does after moving the links
