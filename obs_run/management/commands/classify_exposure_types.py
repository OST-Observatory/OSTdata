from django.core.management.base import BaseCommand
from django.db.models import Q
from django.conf import settings
from obs_run.models import DataFile
from obs_run.ml_classification import ExposureTypeClassifier
from pathlib import Path
import logging
import time

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Classify exposure types for DataFiles using ML model'

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
            help='Show what would be classified without saving',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-classify files that already have exposure_type_ml set',
        )
        parser.add_argument(
            '--format',
            type=str,
            default=None,
            help='Filter by file format (FITS, TIFF, etc.)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']
        force = options['force']
        file_format = options['format']

        # Check if ML classification is enabled
        if not getattr(settings, 'ML_EXPOSURE_TYPE_ENABLED', False):
            self.stdout.write(
                self.style.ERROR('ML_EXPOSURE_TYPE_ENABLED is False in settings. Aborting.')
            )
            return

        # Initialize classifier
        try:
            classifier = ExposureTypeClassifier()
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to initialize classifier: {e}')
            )
            return

        # Build queryset
        queryset = DataFile.objects.all()
        print(f'queryset.count() 1: {queryset.count()}')

        # Determine which formats to filter by
        supported_formats = getattr(settings, 'ML_EXPOSURE_TYPE_SUPPORTED_FORMATS', ['FITS', 'TIFF'])
        formats_to_filter = []
        
        if file_format:
            # If --format is specified, use only that format (if it's supported)
            file_format_upper = file_format.upper()
            if file_format_upper in [f.upper() for f in supported_formats]:
                formats_to_filter = [file_format_upper]
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Format "{file_format}" is not in supported formats: {supported_formats}. '
                        f'Using all supported formats instead.'
                    )
                )
                formats_to_filter = [f.upper() for f in supported_formats]
        else:
            # Use all supported formats
            formats_to_filter = [f.upper() for f in supported_formats]

        # Build format filter query
        format_filters = Q()
        for fmt_upper in formats_to_filter:
            if fmt_upper == 'FITS':
                format_filters |= (
                    Q(file_type__iexact='FITS') |
                    Q(datafile__iendswith='.fits') |
                    Q(datafile__iendswith='.fit') |
                    Q(datafile__iendswith='.fts')
                )
            elif fmt_upper == 'TIFF':
                format_filters |= (
                    Q(file_type__iexact='TIFF') |
                    Q(datafile__iendswith='.tiff') |
                    Q(datafile__iendswith='.tif')
                )
            else:
                format_filters |= Q(file_type__iexact=fmt_upper)
        
        queryset = queryset.filter(format_filters)

        # Filter out already classified files unless --force
        # A file is considered "classified" if exposure_type_ml_confidence is set
        # (this is the best indicator that a real ML classification was performed)
        if not force:
            queryset = queryset.filter(exposure_type_ml_confidence__isnull=True)

        if limit:
            queryset = queryset[:limit]

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No files to classify.'))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN MODE: Would classify {total} files (no database changes will be made)...'
                )
            )
        else:
            self.stdout.write(f'Classifying {total} files...')

        # Tracking variables
        classified = 0
        abstained = 0
        errors = 0
        skipped_format = 0

        start_time = time.time()

        for idx, df in enumerate(queryset, 1):
            try:
                # Check if format is supported
                if not classifier.is_supported_format(df.file_type, Path(df.datafile)):
                    skipped_format += 1
                    continue

                # Classify
                result = classifier.classify_datafile(df)

                if result.get('error'):
                    errors += 1
                    logger.warning(
                        f'Classification error for DataFile {df.pk}: {result["error"]}'
                    )
                    if errors <= 10:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error classifying file {df.pk}: {result["error"]}'
                            )
                        )
                    continue

                # Update DataFile if not dry-run
                if not dry_run:
                    df.exposure_type_ml = result.get('exposure_type_ml')
                    df.exposure_type_ml_confidence = result.get('exposure_type_ml_confidence')
                    df.exposure_type_ml_abstained = result.get('exposure_type_ml_abstained', False)
                    # Set spectrograph if ML detected one and no override is set
                    spectrograph_ml = result.get('spectrograph_ml')
                    update_fields = [
                        'exposure_type_ml',
                        'exposure_type_ml_confidence',
                        'exposure_type_ml_abstained',
                    ]
                    if spectrograph_ml and not df.spectrograph_override:
                        df.spectrograph = spectrograph_ml
                        update_fields.append('spectrograph')
                    df.save(update_fields=update_fields)

                if result.get('exposure_type_ml_abstained', False):
                    abstained += 1
                else:
                    classified += 1

                # Progress display
                processed = classified + abstained + errors
                if processed % max(10, total // 100) == 0 or processed == total:
                    elapsed = time.time() - start_time
                    if processed > 0:
                        rate = processed / elapsed
                        remaining = (total - processed) / rate if rate > 0 else 0
                        percent = (processed / total * 100) if total > 0 else 0
                        self.stdout.write(
                            f'Processed {processed}/{total} ({percent:.1f}%) - '
                            f'Rate: {rate:.1f} files/s - '
                            f'ETA: {remaining:.0f}s'
                        )

            except Exception as e:
                errors += 1
                logger.exception(f'Error processing DataFile {df.pk}: {e}')
                if errors <= 10:
                    self.stdout.write(
                        self.style.ERROR(f'Error on file {df.pk}: {e}')
                    )

        # Summary output
        elapsed_total = time.time() - start_time
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'\nDRY RUN SUMMARY: Would classify {classified} files')
            )
            if abstained > 0:
                self.stdout.write(
                    self.style.WARNING(f'Would abstain on {abstained} files')
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nSuccessfully classified {classified} files')
            )
            if abstained > 0:
                self.stdout.write(
                    self.style.WARNING(f'Model abstained on {abstained} files')
                )

        if skipped_format > 0:
            self.stdout.write(
                self.style.WARNING(f'Skipped {skipped_format} files (unsupported format)')
            )
        if errors > 0:
            self.stdout.write(self.style.ERROR(f'Errors: {errors}'))

        self.stdout.write(f'Total time: {elapsed_total:.1f}s')
