"""
Management command to plate solve existing DataFiles retroactively.

Supports rate limiting to avoid overloading the server.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from pathlib import Path
import time
import logging

from obs_run.models import DataFile
from utilities import annotate_effective_exposure_type
from obs_run.plate_solving import PlateSolvingService, solve_and_update_datafile

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Plate solve existing Light frames with rate limiting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Maximum number of files to process (default: no limit)',
        )
        parser.add_argument(
            '--rate',
            type=float,
            default=2.0,
            help='Maximum files per minute (default: 2.0)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview without saving changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-solve already solved files (if wcs_override=False)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        rate = options['rate']
        dry_run = options['dry_run']
        force = options['force']

        if rate <= 0:
            self.stdout.write(self.style.ERROR('Rate must be > 0'))
            return

        # Calculate delay between files (seconds)
        delay_seconds = 60.0 / rate

        from django.conf import settings
        if not getattr(settings, 'PLATE_SOLVING_ENABLED', False):
            self.stdout.write(self.style.WARNING('Plate solving is disabled in settings'))
            return

        # Query for files to process
        # Exclude spectra: spectrograph != 'N' OR spectroscopy=True
        queryset = DataFile.objects.filter(
            wcs_override=False,
            spectrograph='N',  # Exclude spectra (only process files without spectrograph)
            spectroscopy=False  # Exclude files marked as spectroscopy
        )
        
        if not force:
            queryset = queryset.filter(
                Q(plate_solved=False) | Q(plate_solve_attempted_at__isnull=True)
            )
        
        # Annotate with effective_exposure_type and filter for Light frames
        queryset = annotate_effective_exposure_type(queryset)
        queryset = queryset.filter(annotated_effective_exposure_type='LI')
        
        if limit:
            queryset = queryset[:limit]
        
        files_to_process = list(queryset)
        total_count = len(files_to_process)
        
        if total_count == 0:
            self.stdout.write(self.style.SUCCESS('No files to process'))
            return
        
        self.stdout.write(f'Found {total_count} files to process')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        service = PlateSolvingService()
        if not service.solvers:
            self.stdout.write(self.style.ERROR('No plate solving tools available'))
            return
        
        succeeded = 0
        failed = 0
        skipped = 0
        start_time = time.time()
        
        for idx, datafile in enumerate(files_to_process, 1):
            # Rate limiting: wait if needed
            if idx > 1:
                elapsed = time.time() - start_time
                expected_time = (idx - 1) * delay_seconds
                if elapsed < expected_time:
                    sleep_time = expected_time - elapsed
                    if not dry_run:
                        time.sleep(sleep_time)
            
            self.stdout.write(f'\n[{idx}/{total_count}] Processing file {datafile.pk}: {Path(datafile.datafile).name}')
            
            try:
                # Calculate radius for display
                min_radius, max_radius = service.calculate_radius_from_fov(
                    datafile.fov_x if datafile.fov_x > 0 else -1,
                    datafile.fov_y if datafile.fov_y > 0 else -1
                )
                self.stdout.write(f'  Using radius: {min_radius:.3f} - {max_radius:.3f} degrees')
                
                if dry_run:
                    self.stdout.write(self.style.WARNING('  [DRY RUN] Would attempt plate solving'))
                    # Still try to solve to validate, but don't save
                    result = solve_and_update_datafile(datafile, service=service, save=False)
                    if result['success']:
                        self.stdout.write(self.style.SUCCESS('  [DRY RUN] Would succeed'))
                        succeeded += 1
                    else:
                        self.stdout.write(self.style.ERROR(f'  [DRY RUN] Would fail: {result["error"]}'))
                        failed += 1
                else:
                    result = solve_and_update_datafile(datafile, service=service, save=True)
                    if result['success']:
                        succeeded += 1
                        self.stdout.write(self.style.SUCCESS(f'  ✓ Successfully plate solved'))
                    else:
                        failed += 1
                        self.stdout.write(self.style.ERROR(f'  ✗ {result["error"]}'))
                        
            except Exception as e:
                logger.exception(f'Unexpected error processing file {datafile.pk}: {e}')
                skipped += 1
                self.stdout.write(self.style.ERROR(f'  ✗ Unexpected error: {e}'))
        
        # Summary
        elapsed_time = time.time() - start_time
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  Total processed: {total_count}')
        self.stdout.write(f'  Succeeded: {succeeded}')
        self.stdout.write(f'  Failed: {failed}')
        self.stdout.write(f'  Skipped: {skipped}')
        self.stdout.write(f'  Elapsed time: {elapsed_time:.1f} seconds')
        if not dry_run:
            self.stdout.write(f'  Average rate: {total_count / elapsed_time * 60:.2f} files/minute')
