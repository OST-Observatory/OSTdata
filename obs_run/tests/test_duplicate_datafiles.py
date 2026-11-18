"""Duplicate data file entries (same path): merging them and the unique path constraint."""
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from objects.models import Object
from obs_run.models import DataFile, ObservationRun, PlateSolveFailure

UNIQUE_PATH = next(c for c in DataFile._meta.constraints if c.name == 'datafile_unique_path')
refuse_duplicates = import_module('obs_run.migrations.0024_datafile_unique_path').refuse_duplicates


class UniquePathTest(TestCase):
    def test_paths_are_unique(self):
        run = ObservationRun.objects.create(name='2026-11-01')
        DataFile.objects.create(observation_run=run, datafile='/data/2026-11-01/a.fits', file_type='FITS')
        with self.assertRaises(IntegrityError):
            DataFile.objects.create(observation_run=run, datafile='/data/2026-11-01/a.fits', file_type='FITS')


class MergeDuplicateDatafilesTest(TransactionTestCase):
    """
    Runs without the unique path constraint (state before migration 0024), where duplicates could still
    exist. The constraint is dropped from the current schema instead of migrating back to 0023, so later
    fields of DataFile do not break the test.
    """

    PATH = '/data/2026-10-24/Light/M31_001.fits'

    def setUp(self):
        # Like the migration state, the model must not carry the constraint while the table is changed
        # (SQLite rebuilds the table from the model)
        constraints = DataFile._meta.constraints
        DataFile._meta.constraints = [c for c in constraints if c is not UNIQUE_PATH]
        try:
            with connection.schema_editor() as editor:
                editor.remove_constraint(DataFile, UNIQUE_PATH)
        finally:
            DataFile._meta.constraints = constraints

    def tearDown(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, DataFile._meta.db_table)
        if UNIQUE_PATH.name not in constraints:
            self._add_constraint()

    def _add_constraint(self):
        """What migration 0024 does: refuse duplicates, then add the constraint."""
        refuse_duplicates(apps, None)
        with connection.schema_editor() as editor:
            editor.add_constraint(DataFile, UNIQUE_PATH)

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
        self._add_constraint()

    def test_migration_refuses_duplicates_until_merged(self):
        first, _, _ = self._duplicates()
        with self.assertRaisesMessage(RuntimeError, 'merge_duplicate_datafiles --apply'):
            refuse_duplicates(apps, None)
        first.delete()  # what merge_duplicate_datafiles does after moving the links
