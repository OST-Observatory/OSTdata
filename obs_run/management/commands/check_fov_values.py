from django.core.management.base import BaseCommand
from objects.models import Object
from obs_run.models import DataFile


class Command(BaseCommand):
    help = 'Check FOV values for objects and their associated DataFiles'

    def add_arguments(self, parser):
        parser.add_argument(
            '--object-id',
            type=int,
            help='Check FOV for specific object ID',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Limit number of objects to check (default: 10)',
        )

    def handle(self, *args, **options):
        object_id = options.get('object_id')
        limit = options['limit']
        
        if object_id:
            objects = Object.objects.filter(pk=object_id)
        else:
            # Check stars first (most likely to need FOV)
            objects = Object.objects.filter(object_type='ST')[:limit]
        
        if not objects.exists():
            self.stdout.write(self.style.WARNING('No objects found'))
            return
        
        self.stdout.write(f'Checking FOV values for {objects.count()} object(s)...\n')
        
        for obj in objects:
            self.stdout.write(f'\nObject #{obj.pk}: {obj.name}')
            self.stdout.write(f'  Total DataFiles: {obj.datafiles.count()}')
            
            # Check FOV values
            datafiles_with_fov = obj.datafiles.filter(fov_x__gt=0, fov_y__gt=0)
            fov_count = datafiles_with_fov.count()
            
            self.stdout.write(f'  DataFiles with valid FOV (fov_x > 0, fov_y > 0): {fov_count}')
            
            if fov_count > 0:
                self.stdout.write('  Sample DataFiles with FOV:')
                for df in datafiles_with_fov[:5]:
                    self.stdout.write(
                        f'    DataFile #{df.pk}: fov_x={df.fov_x:.6f}°, '
                        f'fov_y={df.fov_y:.6f}°, exposure_type={df.exposure_type}, '
                        f'file_type={df.file_type}'
                    )
            else:
                # Show sample of all DataFiles to see what FOV values they have
                sample_dfs = obj.datafiles.all()[:5]
                if sample_dfs.exists():
                    self.stdout.write('  Sample DataFiles (all):')
                    for df in sample_dfs:
                        self.stdout.write(
                            f'    DataFile #{df.pk}: fov_x={df.fov_x}, '
                            f'fov_y={df.fov_y}, exposure_type={df.exposure_type}, '
                            f'file_type={df.file_type}, '
                            f'pixel_size={df.pixel_size}, focal_length={df.focal_length}, '
                            f'naxis1={df.naxis1}, naxis2={df.naxis2}'
                        )
        
        # Summary statistics
        self.stdout.write('\n' + '='*60)
        self.stdout.write('SUMMARY')
        self.stdout.write('='*60)
        
        total_objects = Object.objects.count()
        objects_with_fov = Object.objects.filter(
            datafiles__fov_x__gt=0,
            datafiles__fov_y__gt=0
        ).distinct().count()
        
        total_datafiles = DataFile.objects.count()
        datafiles_with_fov = DataFile.objects.filter(
            fov_x__gt=0,
            fov_y__gt=0
        ).count()
        
        self.stdout.write(f'Total Objects: {total_objects}')
        self.stdout.write(f'Objects with at least one DataFile with FOV: {objects_with_fov}')
        self.stdout.write(f'Total DataFiles: {total_datafiles}')
        self.stdout.write(f'DataFiles with valid FOV: {datafiles_with_fov} ({100*datafiles_with_fov/total_datafiles:.1f}%)')

