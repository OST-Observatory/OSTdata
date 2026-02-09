from django.core.management.base import BaseCommand
from django.db.models import Q, F
from django.conf import settings
from obs_run.models import DataFile
from pathlib import Path
import json
import random
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Export DataFiles to JSON for CNN training, grouped by exposure type and spectrograph'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='cnn_training_data.json',
            help='Output JSON file path (default: cnn_training_data.json)',
        )
        parser.add_argument(
            '--max-per-class',
            type=int,
            default=4000,
            help='Maximum number of files per class (default: 4000)',
        )
        parser.add_argument(
            '--min-year',
            type=int,
            default=2021,
            help='Minimum year for observation date (default: 2021)',
        )
        parser.add_argument(
            '--formats',
            nargs='+',
            default=['FITS', 'TIFF'],
            help='File formats to include (default: FITS TIFF)',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=None,
            help='Random seed for reproducibility',
        )
        parser.add_argument(
            '--split',
            nargs=3,
            type=float,
            metavar=('TRAIN', 'VAL', 'TEST'),
            default=[0.7, 0.15, 0.15],
            help='Train/validation/test split ratios (default: 0.7 0.15 0.15)',
        )

    def handle(self, *args, **options):
        output_path = options['output']
        max_per_class = options['max_per_class']
        # Django converts --min-year to min_year in options
        min_year = options.get('min_year') or options.get('min-year', 2021)
        formats = [f.upper() for f in options['formats']]
        seed = options['seed']
        train_ratio, val_ratio, test_ratio = options['split']
        
        # Validate split ratios
        if abs(train_ratio + val_ratio + test_ratio - 1.0) > 0.001:
            self.stdout.write(
                self.style.ERROR(f'Split ratios must sum to 1.0, got {train_ratio + val_ratio + test_ratio}')
            )
            return
        
        if seed is not None:
            random.seed(seed)
        
        self.stdout.write(f'Starting export with parameters:')
        self.stdout.write(f'  Output: {output_path}')
        self.stdout.write(f'  Max per class: {max_per_class}')
        self.stdout.write(f'  Min year: {min_year}')
        self.stdout.write(f'  Formats: {formats}')
        self.stdout.write(f'  Split: train={train_ratio:.1%}, val={val_ratio:.1%}, test={test_ratio:.1%}')
        
        # Get DATA_DIRECTORY from settings
        try:
            import environ
            env = environ.Env()
            environ.Env.read_env()
            data_directory = env("DATA_DIRECTORY", default='/archive/ftp/')
        except Exception:
            data_directory = getattr(settings, 'DATA_DIRECTORY', '/archive/ftp/')
        
        data_directory = Path(data_directory).resolve()
        self.stdout.write(f'  Data directory: {data_directory}')
        
        # Filter files:
        # 1. Files from min_year onwards (obs_date year >= min_year)
        # 2. Only specified formats
        # 3. Only files where exposure_type_user is set OR exposure_type_ml == exposure_type
        queryset = DataFile.objects.filter(
            file_type__in=formats
        )
        
        # Build filter for years >= min_year
        # obs_date is a string field, typically in format "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
        # We need to match all years >= min_year
        year_filters = Q()
        current_year = min_year
        max_year = 2100  # Reasonable upper limit
        for year in range(current_year, max_year + 1):
            year_str = str(year)
            year_filters |= Q(obs_date__startswith=year_str)
        
        queryset = queryset.filter(year_filters)
        
        # Filter for reliable exposure type:
        # exposure_type_user is set OR exposure_type_ml == exposure_type
        queryset = queryset.filter(
            Q(
                Q(exposure_type_user__isnull=False) & ~Q(exposure_type_user='')
            ) | Q(
                Q(exposure_type_ml__isnull=False) &
                ~Q(exposure_type_ml='') &
                Q(exposure_type_ml=F('exposure_type'))
            )
        )
        
        # Select related observation_run for variance
        queryset = queryset.select_related('observation_run')
        
        total_files = queryset.count()
        self.stdout.write(f'Found {total_files} files matching criteria')
        
        # Group files by class
        class_files = defaultdict(list)
        
        for df in queryset.iterator(chunk_size=1000):
            # Determine class based on exposure_type and spectrograph
            # Use exposure_type_user if set, otherwise exposure_type_ml
            # (we've already filtered to ensure one of these is reliable)
            if df.exposure_type_user and df.exposure_type_user.strip():
                exp_type = df.exposure_type_user
            elif df.exposure_type_ml and df.exposure_type_ml.strip():
                exp_type = df.exposure_type_ml
            else:
                # Should not happen due to filter, but skip if it does
                continue
            
            spec = df.spectrograph or 'N'
            
            class_name = self._get_class_name(exp_type, spec)
            if class_name:
                # Get relative path from data directory
                file_path = Path(df.datafile)
                try:
                    relative_path = file_path.relative_to(data_directory)
                    class_files[class_name].append({
                        'path': str(relative_path),
                        'observation_run': df.observation_run_id,
                        'file_type': df.file_type,
                    })
                except ValueError:
                    # File path is not under data_directory, skip it
                    logger.warning(f'File {df.datafile} is not under data directory {data_directory}')
                    continue
        
        # Print statistics
        self.stdout.write('\nFiles per class:')
        for class_name in sorted(class_files.keys()):
            count = len(class_files[class_name])
            self.stdout.write(f'  {class_name}: {count}')
        
        # Sample files per class to ensure variance (different observation runs)
        # and limit to max_per_class
        sampled_files = {}
        for class_name, files in class_files.items():
            if len(files) <= max_per_class:
                sampled_files[class_name] = files
            else:
                # Group by observation_run to ensure variance
                by_run = defaultdict(list)
                for f in files:
                    by_run[f['observation_run']].append(f)
                
                # Sample from each run proportionally
                runs = list(by_run.keys())
                random.shuffle(runs)
                
                sampled = []
                files_per_run = max_per_class // len(runs) if runs else 0
                remaining = max_per_class
                
                for run_id in runs:
                    run_files = by_run[run_id]
                    random.shuffle(run_files)
                    take = min(files_per_run, len(run_files), remaining)
                    sampled.extend(run_files[:take])
                    remaining -= take
                    if remaining <= 0:
                        break
                
                # If we still need more files, randomly sample from remaining
                if remaining > 0:
                    all_sampled_ids = {id(f) for f in sampled}
                    remaining_files = [f for f in files if id(f) not in all_sampled_ids]
                    random.shuffle(remaining_files)
                    sampled.extend(remaining_files[:remaining])
                
                sampled_files[class_name] = sampled[:max_per_class]
            
            self.stdout.write(f'  {class_name}: {len(sampled_files[class_name])} (after sampling)')
        
        # Split into train/val/test
        result = {
            'train': defaultdict(list),
            'val': defaultdict(list),
            'test': defaultdict(list),
        }
        
        for class_name, files in sampled_files.items():
            random.shuffle(files)
            n = len(files)
            n_train = int(n * train_ratio)
            n_val = int(n * val_ratio)
            n_test = n - n_train - n_val  # Remaining goes to test
            
            result['train'][class_name] = [f['path'] for f in files[:n_train]]
            result['val'][class_name] = [f['path'] for f in files[n_train:n_train+n_val]]
            result['test'][class_name] = [f['path'] for f in files[n_train+n_val:]]
        
        # Print split statistics
        self.stdout.write('\nSplit statistics:')
        for split_name in ['train', 'val', 'test']:
            total = sum(len(files) for files in result[split_name].values())
            self.stdout.write(f'  {split_name}: {total} files')
            for class_name in sorted(result[split_name].keys()):
                count = len(result[split_name][class_name])
                if count > 0:
                    self.stdout.write(f'    {class_name}: {count}')
        
        # Write JSON file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully exported to {output_file}')
        )
        self.stdout.write(f'Total files: {sum(len(files) for split in result.values() for files in split.values())}')

    def _get_class_name(self, exposure_type, spectrograph):
        """
        Map exposure_type and spectrograph to CNN class name.
        
        Returns None if the combination doesn't match any class.
        """
        spec = spectrograph or 'N'
        
        if exposure_type == 'BI':
            return 'bias'
        elif exposure_type == 'DA':
            return 'darks'
        elif exposure_type == 'FL':
            if spec == 'N':
                return 'flats'
            elif spec == 'D':
                return 'flat_dados'
            elif spec == 'B':
                return 'flat_baches'
        elif exposure_type == 'LI':
            if spec == 'N':
                return 'deep_sky'  # or 'light'
            elif spec == 'D':
                return 'spectrum_dados'
            elif spec == 'B':
                return 'spectrum_baches'
            elif spec == 'E':
                return 'einsteinturm'
        elif exposure_type == 'WA':
            if spec == 'D':
                return 'wavelength_calibration_dados'
            elif spec == 'B':
                return 'wavelength_calibration_baches'
        
        return None
