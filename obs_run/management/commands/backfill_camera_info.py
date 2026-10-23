from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from obs_run.analyze_fits_header import canonical_instrument, fits_color_sensor
from obs_run.analyze_image_and_video_header import (
    read_ser_header,
    ser_camera_name,
    ser_color_sensor,
    video_frame_size,
)
from obs_run.models import DataFile
from obs_run.utils import should_allow_auto_update
from ostdata.history_reason import REASON_TASK_BACKFILL_CAMERA_INFO, save_with_reason

FILE_KINDS = ('fits', 'ser', 'video')


def _kind_filter(kind):
    if kind == 'fits':
        return (Q(file_type__iexact='FITS') | Q(datafile__iendswith='.fits')
                | Q(datafile__iendswith='.fit') | Q(datafile__iendswith='.fts'))
    if kind == 'ser':
        return Q(file_type__iexact='SER') | Q(datafile__iendswith='.ser')
    return (Q(file_type__iexact='AVI') | Q(file_type__iexact='MOV')
            | Q(datafile__iendswith='.avi') | Q(datafile__iendswith='.mov'))


def camera_info_updates(datafile, kind):
    """Camera fields read from the file that differ from the stored values."""
    updates = {}
    if kind == 'fits':
        color = fits_color_sensor(datafile.get_fits_header())
        if color is not None and datafile.color_sensor != color:
            updates['color_sensor'] = color
    elif kind == 'ser':
        header = read_ser_header(datafile.datafile)
        color = ser_color_sensor(header.get('ColorID'))
        if color is not None and datafile.color_sensor != color:
            updates['color_sensor'] = color
        camera = ser_camera_name(header.get('Instrument'))[:50]
        if camera and camera != datafile.instrument and should_allow_auto_update(datafile, 'instrument'):
            updates['instrument'] = camera
    elif datafile.naxis1 <= 0 or datafile.naxis2 <= 0:
        width, height = video_frame_size(datafile.datafile)
        if width > 0:
            updates['naxis1'], updates['naxis2'] = width, height
    return updates


class Command(BaseCommand):
    help = (
        'Fill camera information for existing files from their headers: sensor type (FITS BAYERPAT, '
        'SER ColorID), camera name (SER) and frame size (AVI/MOV). Only these fields are written; '
        'instrument_normalized is updated on save. Unlike reanalyze_fits, no other header values, '
        'targets or object associations are touched.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only show what would change')
        parser.add_argument('--limit', type=int, default=None, help='Maximum number of files per kind')
        parser.add_argument(
            '--kind', choices=FILE_KINDS, action='append',
            help='File kinds to process (repeatable; default: all)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        kinds = options['kind'] or list(FILE_KINDS)
        changes = Counter()
        errors = 0

        for kind in kinds:
            queryset = DataFile.objects.filter(_kind_filter(kind)).order_by('pk')
            if options['limit']:
                queryset = queryset[:options['limit']]
            checked = changed = 0
            for datafile in queryset.iterator(chunk_size=500):
                checked += 1
                try:
                    updates = camera_info_updates(datafile, kind)
                except Exception as exc:
                    errors += 1
                    if errors <= 10:
                        self.stdout.write(self.style.ERROR(f'  #{datafile.pk} {datafile.datafile}: {exc}'))
                    continue
                if not updates:
                    continue
                changed += 1
                old_normalized = datafile.instrument_normalized
                for field, value in updates.items():
                    setattr(datafile, field, value)
                if not dry_run:
                    # save() adds instrument_normalized to update_fields when it changes
                    save_with_reason(datafile, REASON_TASK_BACKFILL_CAMERA_INFO, update_fields=list(updates))
                    new_normalized = datafile.instrument_normalized
                else:
                    new_normalized = canonical_instrument(
                        datafile.instrument, datafile.naxis1, datafile.naxis2, datafile.pixel_size,
                        datafile.binning_x, datafile.binning_y, datafile.color_sensor,
                    )
                changes[(kind, old_normalized, new_normalized)] += 1
            self.stdout.write(f'{kind}: {checked} files checked, {changed} with new camera information')

        self.stdout.write('  files  kind   instrument_normalized: old -> new')
        for (kind, old, new), count in sorted(changes.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  {count:>7}  {kind:<5}  {old!r} -> {new!r}')
        total = sum(changes.values())
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN: {total} files would change'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{total} files updated'))
        if errors:
            self.stdout.write(self.style.ERROR(f'{errors} files could not be read (missing or unreadable)'))
