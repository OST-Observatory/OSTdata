from django.core.management.base import BaseCommand
from django.db.models import Q
from obs_run.models import DataFile, ObservationRun
from obs_run.analyze_fits_header import analyze_fits
from utilities import evaluate_data_file
from objects.models import Object
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Re-analyze FITS headers to populate new fields (ccd_temp, gain, egain, pedestal, etc.) and re-evaluate object associations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of files to process (for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without saving',
        )
        parser.add_argument(
            '--skip-evaluation',
            action='store_true',
            help='Skip object evaluation (only analyze FITS headers)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        skip_evaluation = options['skip_evaluation']
        
        # Only FITS files
        queryset = DataFile.objects.filter(
            Q(file_type__iexact='FITS') | 
            Q(datafile__iendswith='.fits') |
            Q(datafile__iendswith='.fit') |
            Q(datafile__iendswith='.fts')
        ).select_related('observation_run')
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f'Processing {total} FITS files...')
        if not skip_evaluation:
            self.stdout.write('Will also re-evaluate object associations to update main_target')
        
        # Tracking variables
        updated = 0
        evaluated = 0
        errors = 0
        reassigned_files = []
        skipped_files = []
        new_objects_created = []
        
        start_time = time.time()
        
        for idx, df in enumerate(queryset, 1):
            try:
                if not dry_run:
                    # First analyze FITS header
                    analyze_fits(df)
                    
                    # Then evaluate object associations if requested
                    if not skip_evaluation and df.observation_run:
                        try:
                            # Get existing objects before evaluation
                            existing_object_ids = set(df.object_set.values_list('pk', flat=True))
                            
                            result = evaluate_data_file(df, df.observation_run, skip_if_object_has_overrides=True)
                            
                            if result['status'] == 'assigned':
                                # Check if assignment changed
                                new_object_ids = set(df.object_set.values_list('pk', flat=True))
                                if new_object_ids != existing_object_ids:
                                    # New assignment
                                    new_obj = result.get('object')
                                    file_name = Path(df.datafile).name
                                    reassigned_files.append({
                                        'pk': df.pk,
                                        'file_name': file_name,
                                        'old_object': list(df.object_set.exclude(pk=new_obj.pk).values_list('name', flat=True)) if new_obj else [],
                                        'new_object': new_obj.name if new_obj else 'Unknown'
                                    })
                            elif result['status'] == 'skipped':
                                    file_name = Path(df.datafile).name
                                    skipped_files.append({
                                        'pk': df.pk,
                                        'file_name': file_name,
                                        'reason': result.get('skipped_reason', 'unknown'),
                                        'object': result.get('object').name if result.get('object') else 'Unknown'
                                    })
                            elif result['status'] == 'new_object_created':
                                new_obj = result.get('new_object')
                                if new_obj:
                                    new_objects_created.append(new_obj)
                            
                            evaluated += 1
                        except Exception as eval_error:
                            logger.warning(f'Error evaluating object associations for file {df.pk}: {eval_error}')
                            # Don't count evaluation errors as fatal
                
                updated += 1
                
                # Improved progress display - every 10 files or every 1% whichever is more frequent
                if updated % max(10, total // 100) == 0 or updated == total:
                    elapsed = time.time() - start_time
                    if updated > 0:
                        rate = updated / elapsed
                        remaining = (total - updated) / rate if rate > 0 else 0
                        percent = (updated / total * 100) if total > 0 else 0
                        self.stdout.write(
                            f'Processed {updated}/{total} ({percent:.1f}%) - '
                            f'Rate: {rate:.1f} files/s - '
                            f'ETA: {remaining:.0f}s'
                        )
            except Exception as e:
                errors += 1
                logger.exception(f'Error processing {df.pk}: {e}')
                if errors <= 10: 
                    self.stdout.write(self.style.ERROR(f'Error on file {df.pk}: {e}'))
        
        # After processing: Delete new objects without datafiles
        deleted_objects = []
        if not dry_run and not skip_evaluation:
            for obj in new_objects_created:
                # Refresh from DB to get current state
                obj.refresh_from_db()
                if obj.datafiles.count() == 0:
                    obj_name = obj.name
                    obj.delete()
                    deleted_objects.append(obj_name)
        
        # Summary output
        if dry_run:
            self.stdout.write(self.style.WARNING(f'\nDRY RUN: Would update {updated} files'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated} files'))
            if not skip_evaluation:
                self.stdout.write(self.style.SUCCESS(f'Re-evaluated object associations for {evaluated} files'))
                
                # Summary of reassignments
                if reassigned_files:
                    self.stdout.write(self.style.WARNING(f'\nReassigned {len(reassigned_files)} files:'))
                    if len(reassigned_files) <= 20:
                        for item in reassigned_files:
                            old_str = ', '.join(item['old_object']) if item['old_object'] else 'None'
                            self.stdout.write(f"  File #{item['pk']} ({item['file_name']}): {old_str} -> {item['new_object']}")
                    else:
                        for item in reassigned_files[:10]:
                            old_str = ', '.join(item['old_object']) if item['old_object'] else 'None'
                            self.stdout.write(f"  File #{item['pk']} ({item['file_name']}): {old_str} -> {item['new_object']}")
                        self.stdout.write(f"  ... and {len(reassigned_files) - 10} more")
                
                # Summary of skipped files
                if skipped_files:
                    self.stdout.write(self.style.WARNING(f'\nSkipped {len(skipped_files)} files (objects have override flags):'))
                    if len(skipped_files) <= 20:
                        for item in skipped_files:
                            self.stdout.write(f"  File #{item['pk']} ({item['file_name']}): {item['reason']} (Object: {item['object']})")
                    else:
                        for item in skipped_files[:10]:
                            self.stdout.write(f"  File #{item['pk']} ({item['file_name']}): {item['reason']} (Object: {item['object']})")
                        self.stdout.write(f"  ... and {len(skipped_files) - 10} more")
                
                # Summary of deleted objects
                if deleted_objects:
                    self.stdout.write(self.style.ERROR(f'\nDeleted {len(deleted_objects)} objects without datafiles:'))
                    if len(deleted_objects) <= 20:
                        for obj_name in deleted_objects:
                            self.stdout.write(f"  {obj_name}")
                    else:
                        for obj_name in deleted_objects[:10]:
                            self.stdout.write(f"  {obj_name}")
                        self.stdout.write(f"  ... and {len(deleted_objects) - 10} more")
            
            if errors > 0:
                self.stdout.write(self.style.ERROR(f'\nErrors: {errors}'))

