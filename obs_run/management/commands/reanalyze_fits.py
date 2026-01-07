from django.core.management.base import BaseCommand
from django.db.models import Q
from obs_run.models import DataFile
from obs_run.analyze_fits_header import analyze_fits
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Re-analyze FITS headers to populate new fields (ccd_temp, gain, egain, pedestal, etc.)'

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

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        
        # Only FITS files
        queryset = DataFile.objects.filter(
            Q(file_type__iexact='FITS') | 
            Q(datafile__iendswith='.fits') |
            Q(datafile__iendswith='.fit') |
            Q(datafile__iendswith='.fts')
        )
        
        if limit:
            queryset = queryset[:limit]
        
        total = queryset.count()
        self.stdout.write(f'Processing {total} FITS files...')
        
        updated = 0
        errors = 0
        
        for df in queryset:
            try:
                if not dry_run:
                    analyze_fits(df)
                updated += 1
                if updated % 100 == 0:
                    self.stdout.write(f'Processed {updated}/{total}...')
            except Exception as e:
                errors += 1
                logger.exception(f'Error processing {df.pk}: {e}')
                if errors <= 10: 
                    self.stdout.write(self.style.ERROR(f'Error on file {df.pk}: {e}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: Would update {updated} files'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated} files'))
            if errors > 0:
                self.stdout.write(self.style.WARNING(f'Errors: {errors}'))

