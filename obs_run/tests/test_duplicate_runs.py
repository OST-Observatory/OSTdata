"""Duplicate observation runs: race-safe creation, merging existing duplicates, single watcher."""
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

import utilities
from objects.models import Object
from obs_run.models import DataFile, DownloadJob, ObservationRun
from obs_run.run_merge import merge_runs
from tags.models import Tag
from users.models import User


class RunCreationTest(TestCase):
    def test_same_directory_gives_one_run(self):
        run_dir = Path(tempfile.mkdtemp()) / '2026-10-24'
        run_dir.mkdir()
        utilities.add_new_observation_run(run_dir, add_data_files=True)
        utilities.add_new_observation_run(run_dir, add_data_files=True)
        self.assertEqual(ObservationRun.objects.filter(name='2026-10-24').count(), 1)

    def test_concurrent_creation_returns_the_existing_run(self):
        existing = ObservationRun.objects.create(name='2026-10-12')
        # The other process created the run between our lookup and insert
        with patch.object(ObservationRun.objects, 'get_or_create', side_effect=IntegrityError('duplicate key')):
            run, created = utilities.get_or_create_observation_run('2026-10-12')
        self.assertEqual((run.pk, created), (existing.pk, False))

    def test_run_names_are_unique(self):
        ObservationRun.objects.create(name='2026-10-13')
        with self.assertRaises(IntegrityError):
            ObservationRun.objects.create(name='2026-10-13')


class MergeRunsTest(TestCase):
    def setUp(self):
        # Duplicates cannot be stored any more (unique name): merge two runs directly
        self.keeper = ObservationRun.objects.create(name='2026-10-24', note='')
        self.duplicate = ObservationRun.objects.create(name='2026-10-24-copy', note='Clouds after 23:00',
                                                       reduction_status='PR')
        for idx, (run, hjd) in enumerate(((self.keeper, 2461337.4), (self.duplicate, 2461337.6))):
            DataFile.objects.create(observation_run=run, datafile=f'/tmp/f{idx}.fits', file_type='FITS', hjd=hjd)
        self.user = User.objects.create_user(username='student', password='pw')
        self.duplicate.readonly_users.add(self.user)
        self.tag = Tag.objects.create(name='flats-missing')
        self.duplicate.tags.add(self.tag)
        self.obj = Object.objects.create(name='M 31', is_public=True, object_type='GA')
        self.obj.observation_run.add(self.duplicate)
        self.job = DownloadJob.objects.create(run=self.duplicate)

    def test_dry_run_changes_nothing(self):
        report = merge_runs(self.keeper, [self.duplicate], dry_run=True)
        self.assertEqual((report['datafiles'], report['download_jobs'], report['objects']), (1, 1, 1))
        self.assertTrue(ObservationRun.objects.filter(pk=self.duplicate.pk).exists())

    def test_merge_moves_everything_to_the_oldest_run(self):
        merge_runs(self.keeper, [self.duplicate])
        self.assertFalse(ObservationRun.objects.filter(pk=self.duplicate.pk).exists())
        self.keeper.refresh_from_db()
        self.assertEqual(self.keeper.datafile_set.count(), 2)
        self.assertEqual(DownloadJob.objects.get(pk=self.job.pk).run_id, self.keeper.pk)
        self.assertIn(self.keeper, self.obj.observation_run.all())
        self.assertIn(self.user, self.keeper.readonly_users.all())
        self.assertIn(self.tag, self.keeper.tags.all())
        self.assertEqual((self.keeper.note, self.keeper.reduction_status), ('Clouds after 23:00', 'PR'))
        self.assertAlmostEqual(self.keeper.mid_observation_jd, 2461337.5)

    def test_command_without_duplicates(self):
        out = StringIO()
        call_command('merge_duplicate_runs', stdout=out)
        self.assertIn('No duplicate run names', out.getvalue())


class SingleWatcherTest(TestCase):
    def test_second_watcher_is_refused(self):
        from data_directory_watchdog import acquire_single_instance_lock

        lock_file = Path(tempfile.mkdtemp()) / 'watch.lock'
        with patch.dict(os.environ, {'WATCH_LOCK_FILE': str(lock_file)}):
            first = acquire_single_instance_lock()
            try:
                with self.assertRaises(SystemExit):
                    acquire_single_instance_lock()
            finally:
                first.close()
            # Released with the first process: a new watcher may start
            acquire_single_instance_lock().close()


class UniqueRunNameMigrationTest(TransactionTestCase):
    BEFORE = [('obs_run', '0020_datafile_ai_notice')]
    AFTER = [('obs_run', '0021_observationrun_unique_name')]

    def test_migration_refuses_duplicates_until_merged(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.BEFORE)
        try:
            Run = executor.loader.project_state(self.BEFORE).apps.get_model('obs_run', 'ObservationRun')
            Run.objects.create(name='2026-10-24')
            duplicate = Run.objects.create(name='2026-10-24')
            executor = MigrationExecutor(connection)
            with self.assertRaisesMessage(RuntimeError, 'merge_duplicate_runs --apply'):
                executor.migrate(self.AFTER)
            duplicate.delete()  # what merge_duplicate_runs does after moving the files
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
        self.assertEqual(ObservationRun.objects.filter(name='2026-10-24').count(), 1)
