from django.core.management.base import BaseCommand
from obs_run.models import ObservationRun
from objects.models import Object
from utilities import update_observation_run_photometry_spectroscopy, update_object_photometry_spectroscopy, should_allow_auto_update
import logging
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update photometry and spectroscopy flags for all ObservationRuns and Objects based on associated DataFiles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit-runs',
            type=int,
            default=None,
            help='Limit number of observation runs to process (for testing)',
        )
        parser.add_argument(
            '--limit-objects',
            type=int,
            default=None,
            help='Limit number of objects to process (for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )
        parser.add_argument(
            '--runs-only',
            action='store_true',
            help='Only update observation runs, skip objects',
        )
        parser.add_argument(
            '--objects-only',
            action='store_true',
            help='Only update objects, skip observation runs',
        )

    def handle(self, *args, **options):
        limit_runs = options['limit_runs']
        limit_objects = options['limit_objects']
        dry_run = options['dry_run']
        runs_only = options['runs_only']
        objects_only = options['objects_only']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        start_time = time.time()
        
        # Statistics
        runs_processed = 0
        runs_updated = 0
        runs_skipped_override = 0
        objects_processed = 0
        objects_updated = 0
        objects_skipped_override = 0

        # Process ObservationRuns
        if not objects_only:
            self.stdout.write(self.style.SUCCESS('\n=== Processing Observation Runs ==='))
            
            queryset = ObservationRun.objects.all().order_by('pk')
            if limit_runs:
                queryset = queryset[:limit_runs]
            
            total_runs = queryset.count()
            self.stdout.write(f'Found {total_runs} observation run(s) to process')
            
            for idx, run in enumerate(queryset, 1):
                try:
                    # Check if override flags prevent update
                    can_update_photometry = should_allow_auto_update(run, 'photometry')
                    can_update_spectroscopy = should_allow_auto_update(run, 'spectroscopy')
                    
                    if not can_update_photometry and not can_update_spectroscopy:
                        runs_skipped_override += 1
                        if idx % 100 == 0 or idx == total_runs:
                            self.stdout.write(f'Processed {idx}/{total_runs} runs...')
                        continue
                    
                    # Get current values
                    old_photometry = run.photometry
                    old_spectroscopy = run.spectroscopy
                    
                    # Update flags (this function respects override flags internally)
                    if not dry_run:
                        update_observation_run_photometry_spectroscopy(run)
                        run.refresh_from_db()
                    
                    # Check if values changed
                    new_photometry = run.photometry
                    new_spectroscopy = run.spectroscopy
                    
                    changed = (old_photometry != new_photometry) or (old_spectroscopy != new_spectroscopy)
                    
                    if changed:
                        runs_updated += 1
                        if not dry_run:
                            self.stdout.write(
                                f'  Run #{run.pk} ({run.name}): '
                                f'photometry={old_photometry}→{new_photometry}, '
                                f'spectroscopy={old_spectroscopy}→{new_spectroscopy}'
                            )
                        else:
                            self.stdout.write(
                                f'  [DRY RUN] Run #{run.pk} ({run.name}): '
                                f'would update: photometry={old_photometry}→{new_photometry}, '
                                f'spectroscopy={old_spectroscopy}→{new_spectroscopy}'
                            )
                    
                    runs_processed += 1
                    
                    # Progress indicator
                    if idx % 100 == 0 or idx == total_runs:
                        self.stdout.write(f'Processed {idx}/{total_runs} runs...')
                        
                except Exception as e:
                    logger.warning(f'Error processing observation run {run.pk}: {e}', exc_info=True)
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing run #{run.pk}: {e}')
                    )

        # Process Objects
        if not runs_only:
            self.stdout.write(self.style.SUCCESS('\n=== Processing Objects ==='))
            
            queryset = Object.objects.all().order_by('pk')
            if limit_objects:
                queryset = queryset[:limit_objects]
            
            total_objects = queryset.count()
            self.stdout.write(f'Found {total_objects} object(s) to process')
            
            for idx, obj in enumerate(queryset, 1):
                try:
                    # Check if override flags prevent update
                    can_update_photometry = should_allow_auto_update(obj, 'photometry')
                    can_update_spectroscopy = should_allow_auto_update(obj, 'spectroscopy')
                    
                    if not can_update_photometry and not can_update_spectroscopy:
                        objects_skipped_override += 1
                        if idx % 100 == 0 or idx == total_objects:
                            self.stdout.write(f'Processed {idx}/{total_objects} objects...')
                        continue
                    
                    # Get current values
                    old_photometry = obj.photometry
                    old_spectroscopy = obj.spectroscopy
                    
                    # Update flags (this function respects override flags internally)
                    if not dry_run:
                        update_object_photometry_spectroscopy(obj)
                        obj.refresh_from_db()
                    
                    # Check if values changed
                    new_photometry = obj.photometry
                    new_spectroscopy = obj.spectroscopy
                    
                    changed = (old_photometry != new_photometry) or (old_spectroscopy != new_spectroscopy)
                    
                    if changed:
                        objects_updated += 1
                        if not dry_run:
                            self.stdout.write(
                                f'  Object #{obj.pk} ({obj.name}): '
                                f'photometry={old_photometry}→{new_photometry}, '
                                f'spectroscopy={old_spectroscopy}→{new_spectroscopy}'
                            )
                        else:
                            self.stdout.write(
                                f'  [DRY RUN] Object #{obj.pk} ({obj.name}): '
                                f'would update: photometry={old_photometry}→{new_photometry}, '
                                f'spectroscopy={old_spectroscopy}→{new_spectroscopy}'
                            )
                    
                    objects_processed += 1
                    
                    # Progress indicator
                    if idx % 100 == 0 or idx == total_objects:
                        self.stdout.write(f'Processed {idx}/{total_objects} objects...')
                        
                except Exception as e:
                    logger.warning(f'Error processing object {obj.pk}: {e}', exc_info=True)
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing object #{obj.pk}: {e}')
                    )

        # Summary
        elapsed = time.time() - start_time
        self.stdout.write(self.style.SUCCESS('\n=== Summary ==='))
        self.stdout.write(f'Observation Runs:')
        self.stdout.write(f'  Processed: {runs_processed}')
        self.stdout.write(f'  Updated: {runs_updated}')
        self.stdout.write(f'  Skipped (override flags): {runs_skipped_override}')
        self.stdout.write(f'Objects:')
        self.stdout.write(f'  Processed: {objects_processed}')
        self.stdout.write(f'  Updated: {objects_updated}')
        self.stdout.write(f'  Skipped (override flags): {objects_skipped_override}')
        self.stdout.write(f'\nTotal time: {elapsed:.2f} seconds')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were saved'))
