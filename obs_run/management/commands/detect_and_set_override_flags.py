from django.core.management.base import BaseCommand
from django.db import transaction
import logging

from obs_run.models import ObservationRun, DataFile
from objects.models import Object
from obs_run.utils import get_override_field_name, detect_user_changes_from_history

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Detect existing user changes from HistoricalRecords and set corresponding override flags'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--model',
            type=str,
            choices=['ObservationRun', 'DataFile', 'Object'],
            help='Only process specific model',
        )
        parser.add_argument(
            '--field',
            type=str,
            help='Only process specific field (e.g., mid_observation_jd)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        model_filter = options.get('model')
        field_filter = options.get('field')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))

        # Define field mappings for each model
        model_configs = {
            'ObservationRun': {
                'model': ObservationRun,
                'fields': ['name', 'is_public', 'reduction_status', 'photometry', 
                          'spectroscopy', 'note', 'mid_observation_jd'],
            },
            'DataFile': {
                'model': DataFile,
                'fields': ['exposure_type', 'spectroscopy', 'spectrograph', 
                          'instrument', 'telescope', 'status_parameters'],
            },
            'Object': {
                'model': Object,
                'fields': ['name', 'is_public', 'ra', 'dec', 'first_hjd', 
                          'is_main', 'photometry', 'spectroscopy', 
                          'simbad_resolved', 'object_type', 'note'],
            },
        }

        # Filter models if specified
        if model_filter:
            model_configs = {model_filter: model_configs[model_filter]}

        total_processed = 0
        total_flags_set = 0

        for model_name, config in model_configs.items():
            self.stdout.write(f'\nProcessing {model_name}...')
            model_class = config['model']
            fields = config['fields']

            # Filter fields if specified
            if field_filter:
                if field_filter not in fields:
                    self.stdout.write(
                        self.style.WARNING(f'Field {field_filter} not found in {model_name}')
                    )
                    continue
                fields = [field_filter]

            # Get all instances
            instances = model_class.objects.all()
            count = instances.count()
            self.stdout.write(f'Found {count} {model_name} instances')

            processed = 0
            flags_set = 0

            for instance in instances:
                try:
                    # Detect user changes from history
                    changed_fields = detect_user_changes_from_history(instance)
                    
                    # Filter to only fields we care about
                    relevant_changes = [f for f in changed_fields if f in fields]
                    
                    if not relevant_changes:
                        continue

                    processed += 1
                    update_fields = []

                    for field_name in relevant_changes:
                        override_field_name = get_override_field_name(field_name)
                        if hasattr(instance, override_field_name):
                            current_override = getattr(instance, override_field_name, False)
                            if not current_override:
                                setattr(instance, override_field_name, True)
                                update_fields.append(override_field_name)
                                flags_set += 1
                                self.stdout.write(
                                    f'  {model_name} #{instance.pk}: Setting {override_field_name} '
                                    f'(field {field_name} was changed by user)'
                                )

                    if update_fields and not dry_run:
                        instance.save(update_fields=update_fields)

                except Exception as e:
                    logger.error(f'Error processing {model_name} #{instance.pk}: {e}')
                    self.stdout.write(
                        self.style.ERROR(f'Error on {model_name} #{instance.pk}: {e}')
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f'{model_name}: Processed {processed} instances, set {flags_set} flags'
                )
            )
            total_processed += processed
            total_flags_set += flags_set

        self.stdout.write(
            self.style.SUCCESS(
                f'\nTotal: Processed {total_processed} instances, set {total_flags_set} flags'
            )
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN - No changes were saved. Run without --dry-run to apply changes.')
            )

