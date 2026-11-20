import json
import logging
import random
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from obs_run.ml_classification import ExposureTypeClassifier, apply_ml_result
from obs_run.ml_compare import compare_row, summarize
from obs_run.models import DataFile
from utilities import update_object_photometry_spectroscopy, update_observation_run_photometry_spectroscopy

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Classify exposure types for DataFiles using ML model. With --compare nothing is saved: the configured '
        'classifier is compared with the stored classification (e.g. before rolling out a new model)'
    )

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
        parser.add_argument(
            '--only-unlabelled',
            action='store_true',
            help='Skip files with a manual exposure type (e.g. when re-classifying with a new model)',
        )
        parser.add_argument(
            '--compare',
            action='store_true',
            help='Save nothing; compare the configured classifier with the stored values (ML and effective '
                 'exposure type, spectrograph, accuracy against manual labels). Includes classified files',
        )
        parser.add_argument(
            '--sample',
            type=int,
            default=None,
            help='Random sample of N files (instead of the first N with --limit)',
        )
        parser.add_argument('--seed', type=int, default=0, help='Seed of --sample (default 0)')
        parser.add_argument(
            '--run',
            type=str,
            default=None,
            help='Only files of this observation run (id or name)',
        )
        parser.add_argument('--json', type=str, default=None, help='--compare: write summary and all files')
        parser.add_argument('--examples', type=int, default=3, help='--compare: example files per change')

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

        if options['run']:
            run = options['run']
            queryset = queryset.filter(
                Q(observation_run_id=int(run)) if run.isdigit() else Q(observation_run__name=run)
            )

        # Filter out already classified files unless --force
        # A file is considered "classified" if exposure_type_ml_confidence is set
        # (this is the best indicator that a real ML classification was performed)
        if not force and not options['compare']:
            queryset = queryset.filter(exposure_type_ml_confidence__isnull=True)
        if options['only_unlabelled']:
            queryset = queryset.filter(Q(exposure_type_user__isnull=True) | Q(exposure_type_user=''))

        if options['sample']:
            ids = list(queryset.order_by('pk').values_list('pk', flat=True))
            ids = random.Random(options['seed']).sample(ids, min(options['sample'], len(ids)))
            queryset = DataFile.objects.filter(pk__in=ids).order_by('pk')
        elif limit:
            queryset = queryset[:limit]

        if options['compare']:
            self._compare(classifier, queryset.select_related('observation_run'), options)
            return

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
                    df.save(update_fields=apply_ml_result(df, result))
                    
                    # Automatically update photometry/spectroscopy flags for associated observation runs and objects
                    # Update observation run
                    if df.observation_run:
                        update_observation_run_photometry_spectroscopy(df.observation_run)
                    
                    # Update all associated objects
                    for obj in df.object_set.all():
                        update_object_photometry_spectroscopy(obj)

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

    def _compare(self, classifier, queryset, options):
        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No files to compare.'))
            return
        self.stdout.write(f'Comparing {total} files (nothing is saved)...')
        rows, errors, skipped = [], 0, 0
        start = time.time()
        for idx, df in enumerate(queryset, 1):
            if not classifier.is_supported_format(df.file_type, Path(df.datafile)):
                skipped += 1
                continue
            try:
                result = classifier.classify_datafile(df)
            except Exception as e:
                result = {'error': str(e)}
            if result.get('error'):
                errors += 1
                if errors <= 10:
                    self.stdout.write(self.style.ERROR(f'Error on file {df.pk}: {result["error"]}'))
                continue
            rows.append(compare_row(df, result))
            if idx % 100 == 0:
                rate = idx / (time.time() - start)
                self.stdout.write(f'{idx}/{total} ({rate:.1f} files/s, ETA {(total - idx) / rate:.0f}s)')

        summary = summarize(rows, examples=options['examples'])
        summary.update({'errors': errors, 'skipped_format': skipped, 'sample': options['sample'],
                        'seed': options['seed'] if options['sample'] else None, 'run': options['run'],
                        'model': str(getattr(settings, 'ML_EXPOSURE_TYPE_MODEL_PATH', ''))})
        self._print_comparison(summary, time.time() - start)
        if options['json']:
            with open(options['json'], 'w') as f:
                json.dump({'summary': summary, 'files': rows}, f, indent=1, default=str)
            self.stdout.write(f'Written to {options["json"]}')

    def _print_changes(self, changes, top=10):
        for entry in changes[:top]:
            self.stdout.write(f'    {entry["change"]:<10} {entry["n"]:>6}')
            for path in entry['examples']:
                self.stdout.write(f'        {path}')

    def _print_comparison(self, s, elapsed):
        def pct(value):
            return '-' if value is None else f'{100 * value:.1f} %'

        self.stdout.write(f'\nCompared {s["files"]} files in {elapsed:.0f}s '
                          f'(errors {s["errors"]}, unsupported format {s["skipped_format"]})')
        self.stdout.write(f'\nML exposure type, old -> new ("-" = ML never ran), '
                          f'{sum(c["n"] for c in s["ml_changes"])} changed:')
        self._print_changes(s['ml_changes'])

        u = s['without_manual_label']
        self.stdout.write(f'\nEffective exposure type, files without manual label (n={u["n"]}): '
                          f'UK (review queue) {u["uk_before"]} -> {u["uk_after"]}')
        self._print_changes(u['changes'])

        m = s['with_manual_label']
        self.stdout.write(f'\nML suggestion against the manual label (n={m["new"]["n"]}):')
        for name in ('old', 'new'):
            q = m[name]
            self.stdout.write(f'    {name:<4} correct {pct(q["correct"]):>8}   abstained/not run '
                              f'{pct(q["abstained_or_not_run"]):>8}   wrong {pct(q["wrong"]):>8}')
        if m['new_errors']:
            self.stdout.write('  Wrong new suggestions (manual -> new):')
            self._print_changes(m['new_errors'])

        sp = s['spectrograph']
        self.stdout.write('\nSpectrograph, files without manual value, old -> new:')
        self._print_changes(sp['changes_without_manual_value'])
        manual = sp['manual']
        self.stdout.write(f'Spectrograph, manually set (n={manual["n"]}): new automatic value correct '
                          f'{pct(manual["new_correct"])}; old {pct(manual["old_correct"])} '
                          f'(n={manual["old_n"]} with stored ML suggestion)')
