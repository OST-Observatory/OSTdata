from django.core.management.base import BaseCommand
from django.db import transaction
import logging
import math

from objects.models import Object
from utilities import (
    get_object_fov_radius,
    detect_object_type_from_simbad_types,
    update_object_from_simbad_result,
    _query_region_safe,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reevaluate stars by searching SIMBAD with extended radius to find nearby clusters, nebulae, and galaxies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name-filter',
            type=str,
            help='Filter stars by name pattern (e.g., "TYC" for TYC stars)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Process only N objects (for testing)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--radius-fallback',
            type=float,
            default=5.0,
            help='Fixed radius in arcmin if FOV unavailable (default: 5.0)',
        )
        parser.add_argument(
            '--min-radius',
            type=float,
            default=1.0,
            help='Minimum search radius in arcmin (default: 1.0)',
        )
        parser.add_argument(
            '--max-radius',
            type=float,
            default=30.0,
            help='Maximum search radius in arcmin (default: 30.0)',
        )

    def handle(self, *args, **options):
        name_filter = options.get('name_filter')
        limit = options.get('limit')
        dry_run = options['dry_run']
        radius_fallback = options['radius_fallback']
        min_radius = options['min_radius']
        max_radius = options['max_radius']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be saved'))
        
        # Query stars
        queryset = Object.objects.filter(object_type='ST')
        
        # Apply name filter if provided
        if name_filter:
            queryset = queryset.filter(name__icontains=name_filter)
            self.stdout.write(f'Filtering stars with name containing: "{name_filter}"')
        
        # Apply limit if provided
        if limit:
            queryset = queryset[:limit]
        
        total_count = queryset.count()
        self.stdout.write(f'\nFound {total_count} star(s) to process')
        
        if total_count == 0:
            self.stdout.write(self.style.WARNING('No stars found matching criteria'))
            return
        
        # Priority order: NE > SC > GA
        priority_types = ['NE', 'SC', 'GA']
        
        stats = {
            'processed': 0,
            'updated': 0,
            'no_match': 0,
            'override_blocked': 0,
            'errors': 0,
        }
        
        for obj in queryset:
            try:
                stats['processed'] += 1
                self.stdout.write(f'\nProcessing star #{obj.pk}: {obj.name} (RA={obj.ra:.6f}, Dec={obj.dec:.6f})')
                
                # Skip if coordinates are invalid
                if obj.ra == -1 or obj.dec == -1 or obj.ra == 0 or obj.dec == 0:
                    self.stdout.write(self.style.WARNING(f'  Skipping: Invalid coordinates'))
                    continue
                
                # Calculate FOV radius
                radius_str = get_object_fov_radius(
                    obj,
                    fallback_arcmin=radius_fallback,
                    min_arcmin=min_radius,
                    max_arcmin=max_radius
                )
                self.stdout.write(f'  Using search radius: {radius_str}')
                
                # Query SIMBAD
                self.stdout.write(f'  Querying SIMBAD...')
                result_table = _query_region_safe(
                    obj.ra,
                    obj.dec,
                    radius_str,
                    row_limit=50  # Increased limit for extended search
                )
                
                if result_table is None or len(result_table) == 0:
                    self.stdout.write(self.style.WARNING('  No SIMBAD results found'))
                    stats['no_match'] += 1
                    continue
                
                self.stdout.write(f'  Found {len(result_table)} SIMBAD object(s)')
                
                # Filter results for SC, NE, GA types and apply priority
                candidates = []
                for row in result_table:
                    raw_types = row.get('alltypes.otypes', None)
                    types_str = '' if raw_types is None else str(raw_types)
                    detected_type = detect_object_type_from_simbad_types(types_str)
                    
                    if detected_type in priority_types:
                        # Calculate distance (simple angular distance)
                        simbad_ra = float(row['ra'])
                        simbad_dec = float(row['dec'])
                        # Simple angular distance approximation (good for small angles)
                        ra_diff = (simbad_ra - obj.ra) * math.cos(math.radians(obj.dec))
                        dec_diff = simbad_dec - obj.dec
                        distance_deg = math.sqrt(ra_diff**2 + dec_diff**2)
                        
                        candidates.append({
                            'row': row,
                            'type': detected_type,
                            'distance_deg': distance_deg,
                            'name': str(row.get('main_id', 'Unknown')),
                        })
                
                if not candidates:
                    self.stdout.write(self.style.WARNING('  No SC/NE/GA objects found in results'))
                    stats['no_match'] += 1
                    continue
                
                # Sort by priority (NE > SC > GA) and then by distance
                priority_order = {t: i for i, t in enumerate(priority_types)}
                candidates.sort(key=lambda x: (
                    priority_order.get(x['type'], 999),  # Lower priority number = higher priority
                    x['distance_deg']  # Then by distance
                ))
                
                best_match = candidates[0]
                self.stdout.write(
                    f'  Best match: {best_match["name"]} '
                    f'(type={best_match["type"]}, distance={best_match["distance_deg"]:.6f} deg)'
                )
                
                # Update object
                update_result = update_object_from_simbad_result(
                    obj,
                    best_match['row'],
                    priority_types=priority_types,
                    dry_run=dry_run
                )
                
                if update_result['updated_fields']:
                    stats['updated'] += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  Updated fields: {", ".join(update_result["updated_fields"])}'
                        )
                    )
                    if update_result['new_object_type']:
                        self.stdout.write(
                            f'    New object type: {update_result["new_object_type"]}'
                        )
                    if update_result['new_name']:
                        self.stdout.write(
                            f'    New name: {update_result["new_name"]}'
                        )
                    if update_result.get('identifiers_deleted', 0) > 0:
                        self.stdout.write(
                            f'    Deleted {update_result["identifiers_deleted"]} old identifier(s)'
                        )
                    if update_result.get('identifiers_created', 0) > 0:
                        self.stdout.write(
                            f'    Created {update_result["identifiers_created"]} new identifier(s)'
                        )
                else:
                    # Check if override flags blocked updates
                    from obs_run.utils import should_allow_auto_update
                    blocked_fields = []
                    if not should_allow_auto_update(obj, 'object_type'):
                        blocked_fields.append('object_type')
                    if not should_allow_auto_update(obj, 'ra'):
                        blocked_fields.append('ra')
                    if not should_allow_auto_update(obj, 'dec'):
                        blocked_fields.append('dec')
                    if not should_allow_auto_update(obj, 'name'):
                        blocked_fields.append('name')
                    
                    if blocked_fields:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  Updates blocked by override flags: {", ".join(blocked_fields)}'
                            )
                        )
                        stats['override_blocked'] += 1
                    else:
                        self.stdout.write(self.style.WARNING('  No updates needed'))
                
            except Exception as e:
                logger.exception(f'Error processing star #{obj.pk}: {e}')
                self.stdout.write(
                    self.style.ERROR(f'  Error: {e}')
                )
                stats['errors'] += 1
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write('='*60)
        self.stdout.write(f'Processed: {stats["processed"]}')
        self.stdout.write(f'Updated: {stats["updated"]}')
        self.stdout.write(f'No match found: {stats["no_match"]}')
        self.stdout.write(f'Override blocked: {stats["override_blocked"]}')
        self.stdout.write(f'Errors: {stats["errors"]}')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nDRY RUN - No changes were saved. Run without --dry-run to apply changes.')
            )

