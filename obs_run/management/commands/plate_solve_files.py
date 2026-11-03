"""
Management command to plate solve existing DataFiles retroactively.

Supports rate limiting to avoid overloading the server. --compare re-solves already solved files
without saving and reports the deviation from the stored solution (e.g. ASTAP vs. Watney).
"""

import logging
import time
import warnings
from pathlib import Path

import numpy as np
from django.conf import settings
from django.core.management.base import BaseCommand

from obs_run.models import DataFile
from obs_run.plate_solving import PlateSolvingService, plate_solve_candidates, solve_and_update_datafile

logger = logging.getLogger(__name__)


def _wcs_of(datafile):
    from astropy.wcs import WCS

    from obs_run.sky_view import datafile_wcs_header

    header = datafile_wcs_header(datafile)
    if header is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return WCS(header)


def compare_solutions(old_wcs, new_wcs, naxis1, naxis2):
    """(center offset, largest corner offset) in arcsec and the pixel scale ratio new/old."""
    from astropy.coordinates import SkyCoord
    from astropy.wcs.utils import proj_plane_pixel_scales

    pixels = [[(naxis1 + 1) / 2, (naxis2 + 1) / 2], [1, 1], [naxis1, 1], [1, naxis2], [naxis1, naxis2]]
    old = SkyCoord(*old_wcs.all_pix2world(pixels, 1).T, unit='deg')
    new = SkyCoord(*new_wcs.all_pix2world(pixels, 1).T, unit='deg')
    offsets = old.separation(new).arcsec
    ratio = float(np.mean(proj_plane_pixel_scales(new_wcs)) / np.mean(proj_plane_pixel_scales(old_wcs)))
    return float(offsets[0]), float(np.max(offsets[1:])), ratio


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
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help='Also try solvers that failed for a file before (default: each solver once per file)',
        )
        parser.add_argument(
            '--tool',
            action='append',
            help='Only use this solver (repeatable, e.g. --tool astap); default: PLATE_SOLVING_TOOLS',
        )
        parser.add_argument(
            '--compare',
            action='store_true',
            help='Re-solve already solved files without saving and report the deviation from the stored solution',
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

        compare = options['compare']
        # Re-solving solved files or explicit retries: all solvers, also those that failed before
        retry_all = compare or force or options['retry_failed']
        if compare:
            # Read-only: allowed also while the plate solving task is switched off
            dry_run = True
            queryset = DataFile.objects.filter(plate_solved=True, wcs_crval1__isnull=False).order_by('-pk')
        elif not getattr(settings, 'PLATE_SOLVING_ENABLED', False):
            self.stdout.write(self.style.WARNING('Plate solving is disabled in settings'))
            return
        else:
            queryset = plate_solve_candidates(
                force=force, retry_failed=options['retry_failed'], tools=options['tool'],
            )

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
        
        service = PlateSolvingService(tools=options['tool'])
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
                
                if compare:
                    old_wcs = _wcs_of(datafile)
                    result = solve_and_update_datafile(datafile, service=service, save=False, retry_failed=retry_all)
                    new_wcs = _wcs_of(datafile) if result['success'] else None
                    if old_wcs is None or new_wcs is None:
                        failed += 1
                        self.stdout.write(self.style.ERROR(f'  ✗ {result["error"] or "no WCS to compare"}'))
                        continue
                    center, corner, ratio = compare_solutions(
                        old_wcs, new_wcs, int(datafile.naxis1), int(datafile.naxis2),
                    )
                    succeeded += 1
                    line = (f'  {result["tool"]}: center {center:.1f}", corners up to {corner:.1f}", '
                            f'scale ratio {ratio:.4f}')
                    # Corners far apart while the center matches: mirrored or rotated solution
                    style = self.style.SUCCESS if corner < 10 and abs(ratio - 1) < 0.01 else self.style.WARNING
                    self.stdout.write(style(line))
                elif dry_run:
                    self.stdout.write(self.style.WARNING('  [DRY RUN] Would attempt plate solving'))
                    # Still try to solve to validate, but don't save
                    result = solve_and_update_datafile(datafile, service=service, save=False, retry_failed=retry_all)
                    if result['success']:
                        self.stdout.write(self.style.SUCCESS('  [DRY RUN] Would succeed'))
                        succeeded += 1
                    else:
                        self.stdout.write(self.style.ERROR(f'  [DRY RUN] Would fail: {result["error"]}'))
                        failed += 1
                else:
                    result = solve_and_update_datafile(datafile, service=service, save=True, retry_failed=retry_all)
                    if result['success']:
                        succeeded += 1
                        self.stdout.write(self.style.SUCCESS('  ✓ Successfully plate solved'))
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
