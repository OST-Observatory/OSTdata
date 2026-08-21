from __future__ import annotations

from pathlib import Path
from typing import Optional

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework.serializers import (
    ModelSerializer,
    PrimaryKeyRelatedField,
    SerializerMethodField,
)

from objects.api.simple_serializers import ObjectSimpleSerializer
from obs_run.models import DataFile, ObservationRun
from obs_run.search import find_aux_object_search_match
from obs_run.utils import INSTRUMENT_ALIASES, TELESCOPE_ALIASES, normalize_alias
from tags.api.serializers import TagSerializer
from tags.models import Tag

# ===============================================================
#   OBSERVATION RUNS
# ===============================================================


# (RunListSerializer removed; unified into RunSerializer)

    # (legacy alias getters removed)


################################################################################


class RunSerializer(ModelSerializer):
    tags = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )
    href = SerializerMethodField()
    reduction_status_display = SerializerMethodField()
    n_datafiles = SerializerMethodField()
    n_fits = SerializerMethodField()
    n_img = SerializerMethodField()
    n_ser = SerializerMethodField()
    # Exposure-type counts (robust fallback)
    n_light = SerializerMethodField()
    n_flat = SerializerMethodField()
    n_dark = SerializerMethodField()
    expo_time = SerializerMethodField()
    light_expo_time = SerializerMethodField()
    start_time = SerializerMethodField()
    end_time = SerializerMethodField()
    objects = SerializerMethodField()
    search_match_via_aux = SerializerMethodField()
    # ObservationRun.added_by was removed; keep API key for compatibility (always null).
    owner = SerializerMethodField()

    class Meta:
        model = ObservationRun
        fields = [
            'pk',
            'name',
            'reduction_status',
            'reduction_status_display',
            'note',
            'photometry',
            'spectroscopy',
            'tags',
            'tag_ids',
            'href',
            'owner',
            'n_datafiles',
            'n_fits',
            'n_img',
            'n_ser',
            'n_light',
            'n_flat',
            'n_dark',
            'expo_time',
            'light_expo_time',
            'start_time',
            'end_time',
            'objects',
            'search_match_via_aux',
            'mid_observation_jd',
            'is_public',
            # Override flags (read-only for normal users, editable for admins)
            'name_override',
            'is_public_override',
            'reduction_status_override',
            'photometry_override',
            'spectroscopy_override',
            'note_override',
            'mid_observation_jd_override',
        ]
        read_only_fields = ('pk', 'tags', 'reduction_status_display', 'owner')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make override flags read-only for non-admin users
        request = self.context.get('request')
        if request and not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
            for field_name in ['name_override', 'is_public_override', 'reduction_status_override',
                             'photometry_override', 'spectroscopy_override', 'note_override',
                             'mid_observation_jd_override']:
                if field_name in self.fields:
                    self.fields[field_name].read_only = True

    @extend_schema_field(OpenApiTypes.STR)
    def get_owner(self, obj) -> Optional[str]:
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_href(self, obj) -> str:
        # Return SPA route instead of Django reverse (legacy templates removed)
        return f"/observation-runs/{obj.pk}"

    @extend_schema_field(TagSerializer(many=True))
    def get_tags(self, obj) -> list:
        #   This has to be used instead of a through field, as otherwise
        #   PUT or PATCH requests fail!
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    @extend_schema_field(OpenApiTypes.STR)
    def get_reduction_status_display(self, obj) -> str:
        return obj.get_reduction_status_display()

    def _get_annotated_or(self, obj, name, fallback_callable):
        try:
            v = getattr(obj, name, None)
            if isinstance(v, (int, float)) and v >= 0:
                return int(v)
        except Exception:
            pass
        try:
            return int(fallback_callable())
        except Exception:
            return 0

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_datafiles(self, obj) -> int:
        return self._get_annotated_or(obj, 'n_datafiles', lambda: obj.datafile_set.count())

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_fits(self, obj) -> int:
        return self._get_annotated_or(
            obj,
            'n_fits',
            lambda: obj.datafile_set.filter(file_type__exact='FITS').count(),
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_img(self, obj) -> int:
        return self._get_annotated_or(
            obj,
            'n_img',
            lambda: (
                obj.datafile_set.filter(file_type__exact='JPG').count()
                + obj.datafile_set.filter(file_type__exact='CR2').count()
                + obj.datafile_set.filter(file_type__exact='TIFF').count()
            ),
        )

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_ser(self, obj) -> int:
        return self._get_annotated_or(
            obj,
            'n_ser',
            lambda: obj.datafile_set.filter(file_type__exact='SER').count(),
        )

    # Robust exposure-type counters (tolerant to variant values)
    def _count_exptype(self, obj, codes_or_prefixes):
        try:
            # Prefer annotated value if present and positive (detail may also carry annotations)
            ann_key = codes_or_prefixes.get('ann')
            if ann_key:
                v = getattr(obj, ann_key, None)
                if isinstance(v, (int, float)) and v > 0:
                    return int(v)
        except Exception:
            pass
        try:
            qs = obj.datafile_set.all()
            from django.db.models import Q
            q = Q()
            for code in codes_or_prefixes.get('codes', []):
                q |= Q(exposure_type__iexact=code)
                q |= Q(exposure_type__iregex=rf'^\\s*{code.lower()}\\s*$')
            for pref in codes_or_prefixes.get('prefixes', []):
                q |= Q(exposure_type__istartswith=pref)
            return qs.filter(q).count()
        except Exception:
            return 0

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_light(self, obj) -> int:
        return self._count_exptype(obj, {'ann': 'n_light', 'codes': ['LI'], 'prefixes': ['LIGHT']})

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_flat(self, obj) -> int:
        return self._count_exptype(obj, {'ann': 'n_flat', 'codes': ['FL'], 'prefixes': ['FLAT']})

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_dark(self, obj) -> int:
        return self._count_exptype(obj, {'ann': 'n_dark', 'codes': ['DA'], 'prefixes': ['DARK']})

    # (legacy alias getters removed)

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_expo_time(self, obj) -> float:
        try:
            v = getattr(obj, 'expo_time', None)
            if isinstance(v, (int, float)) and v >= 0:
                return float(v)
        except Exception:
            pass
        data_files = obj.datafile_set.all()
        total_expo_time = 0.0
        for f in data_files:
            expo_time = getattr(f, 'exptime', 0) or 0
            if expo_time > 0:
                total_expo_time += float(expo_time)
        return total_expo_time

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_light_expo_time(self, obj) -> float:
        """Total exposure time of Light (LI) frames only."""
        try:
            v = getattr(obj, 'light_expo_time', None)
            if isinstance(v, (int, float)) and v >= 0:
                return float(v)
        except Exception:
            pass
        try:
            from utilities import annotate_effective_exposure_type
            total = 0.0
            light_files = annotate_effective_exposure_type(obj.datafile_set.all()).filter(
                annotated_effective_exposure_type='LI'
            )
            for f in light_files.only('exptime'):
                ex = getattr(f, 'exptime', 0) or 0
                if ex > 0:
                    total += float(ex)
            return total
        except Exception:
            return 0.0

    @extend_schema_field(OpenApiTypes.STR)
    def get_start_time(self, obj) -> str:
        # Return ISO-8601 timestamp
        data_files = obj.datafile_set.filter(hjd__gt=2451545).order_by('hjd')
        if data_files.exists():
            dt = data_files.first().obs_date
            try:
                if hasattr(dt, 'isoformat'):
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt, timezone.get_current_timezone())
                    return dt.isoformat()
                if isinstance(dt, str):
                    return dt
            except Exception:
                pass
            return '2000-01-01T00:00:00Z'
        return '2000-01-01T00:00:00Z'

    @extend_schema_field(OpenApiTypes.STR)
    def get_end_time(self, obj) -> str:
        # Return ISO-8601 timestamp
        data_files = obj.datafile_set.filter(hjd__gt=2451545).order_by('-hjd')
        if data_files.exists():
            dt = data_files.first().obs_date
            try:
                if hasattr(dt, 'isoformat'):
                    if timezone.is_naive(dt):
                        dt = timezone.make_aware(dt, timezone.get_current_timezone())
                    return dt.isoformat()
                if isinstance(dt, str):
                    return dt
            except Exception:
                pass
            return '2000-01-01T00:00:00Z'
        return '2000-01-01T00:00:00Z'

    @extend_schema_field(ObjectSimpleSerializer(many=True))
    def get_objects(self, obj) -> list:
        objects = ObjectSimpleSerializer(obj.object_set.all(), many=True).data
        return objects

    @extend_schema_field(OpenApiTypes.STR)
    def get_search_match_via_aux(self, obj) -> Optional[str]:
        aux_search = self.context.get('aux_object')
        if not aux_search:
            return None
        return find_aux_object_search_match(obj, aux_search)


################################################################################


class SimpleRunSerializer(ModelSerializer):
    """
   Basic serializer only returning the most basic information
   available for the ObservationRun object
   """

    href = SerializerMethodField()

    class Meta:
        model = ObservationRun
        fields = [
            'pk',
            'name',
            'href',
        ]
        read_only_fields = ('pk',)

    @extend_schema_field(OpenApiTypes.STR)
    def get_href(self, obj) -> str:
        # Return SPA route instead of Django reverse (legacy templates removed)
        return f"/observation-runs/{obj.pk}"


# ===============================================================
#   DATA FILE
# ===============================================================

class DataFileSerializer(ModelSerializer):
    tags = SerializerMethodField()
    exposure_type_display = SerializerMethodField()
    effective_exposure_type = SerializerMethodField()
    effective_exposure_type_display = SerializerMethodField()
    exposure_type_ml_display = SerializerMethodField()
    exposure_type_user_display = SerializerMethodField()
    binning = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )
    file_name = SerializerMethodField()
    download_url = SerializerMethodField()
    observation_run_name = SerializerMethodField()
    object_ids = SerializerMethodField()
    main_object_id = SerializerMethodField()
    main_object_name = SerializerMethodField()
    ra_hms = SerializerMethodField()
    dec_dms = SerializerMethodField()
    ra_hms = SerializerMethodField()
    dec_dms = SerializerMethodField()

    class Meta:
        model = DataFile
        fields = [
            'pk',
            'observation_run',
            'observation_run_name',
            'file_name',
            'download_url',
            'file_type',
            'instrument',
            'telescope',
            'binning',
            'exposure_type',
            'exposure_type_display',
            # Effective exposure type (priority-based)
            'effective_exposure_type',
            'effective_exposure_type_display',
            # ML-based exposure type classification
            'exposure_type_ml',
            'exposure_type_ml_display',
            'exposure_type_ml_confidence',
            'exposure_type_ml_abstained',
            # User-set exposure type
            'exposure_type_user',
            'exposure_type_user_display',
            'exposure_type_user_override',
            'tags',
            'tag_ids',
            # 'added_by',
            'content_hash',
            'file_size',
            'hjd',
            'obs_date',
            'exptime',
            'naxis1',
            'naxis2',
            'main_target',
            'header_target_name',
            'object_ids',
            'main_object_id',
            'main_object_name',
            'ra',
            'dec',
            'ra_hms',
            'dec_dms',
            'status_parameters',
            'spectrograph',
            'spectroscopy',
            # Override flags (read-only for normal users, editable for admins)
            'exposure_type_override',
            'spectroscopy_override',
            'spectrograph_override',
            'instrument_override',
            'telescope_override',
            'status_parameters_override',
            # Plate solving fields
            'plate_solved',
            'plate_solve_attempted_at',
            'plate_solve_error',
            'plate_solve_tool',
            'wcs_override',
            # WCS fields
            'wcs_ra',
            'wcs_dec',
            'wcs_ra_hms',
            'wcs_dec_dms',
            'wcs_field_radius',
            'wcs_orientation',
            'wcs_pix_scale',
            'wcs_parity',
            'wcs_field_width',
            'wcs_field_height',
            'wcs_cd1_1',
            'wcs_cd1_2',
            'wcs_cd2_1',
            'wcs_cd2_2',
            'wcs_cdelt1',
            'wcs_cdelt2',
            'wcs_crota1',
            'wcs_crota2',
            'wcs_crpix1',
            'wcs_crpix2',
            'wcs_crval1',
            'wcs_crval2',
        ]
        read_only_fields = (
            'pk',
            'observation_run',
            'content_hash',
            'file_size',
            'plate_solved',
            'plate_solve_attempted_at',
            'plate_solve_error',
            'plate_solve_tool',
            'wcs_override',
            'wcs_ra',
            'wcs_dec',
            'wcs_ra_hms',
            'wcs_dec_dms',
            'wcs_field_radius',
            'wcs_orientation',
            'wcs_pix_scale',
            'wcs_parity',
            'wcs_field_width',
            'wcs_field_height',
            'wcs_cd1_1',
            'wcs_cd1_2',
            'wcs_cd2_1',
            'wcs_cd2_2',
            'wcs_cdelt1',
            'wcs_cdelt2',
            'wcs_crota1',
            'wcs_crota2',
            'wcs_crpix1',
            'wcs_crpix2',
            'wcs_crval1',
            'wcs_crval2',
            'naxis1',
            'naxis2',
            'hjd',
            'obs_date',
            'exptime',
            'ra',
            'dec',
            'ra_hms',
            'dec_dms',
            'file_type',
            'exposure_type_ml',
            'exposure_type_ml_confidence',
            'exposure_type_ml_abstained',
        )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make override flags read-only for non-admin users
        request = self.context.get('request')
        if request and not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
            for field_name in ['exposure_type_override', 'spectroscopy_override', 'spectrograph_override',
                             'instrument_override', 'telescope_override', 'status_parameters_override',
                             'exposure_type_user_override']:
                if field_name in self.fields:
                    self.fields[field_name].read_only = True

    @extend_schema_field(TagSerializer(many=True))
    def get_tags(self, obj) -> list:
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    @extend_schema_field(OpenApiTypes.STR)
    def get_file_name(self, obj) -> str:
        path = Path(obj.datafile)
        return path.name

    @extend_schema_field(OpenApiTypes.URI)
    def get_download_url(self, obj) -> str:
        return f"/api/runs/datafiles/{obj.pk}/download/"

    @extend_schema_field(OpenApiTypes.STR)
    def get_exposure_type_display(self, obj) -> Optional[str]:
        # Return effective exposure type display instead of raw exposure_type
        return obj.get_effective_exposure_type_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_effective_exposure_type(self, obj) -> Optional[str]:
        # Check for annotated_effective_exposure_type first (used to avoid property conflicts)
        if hasattr(obj, '__dict__') and 'annotated_effective_exposure_type' in obj.__dict__:
            return obj.__dict__['annotated_effective_exposure_type']
        # Check if effective_exposure_type is an annotated field (from QuerySet annotation)
        if hasattr(obj, '__dict__') and 'effective_exposure_type' in obj.__dict__:
            return obj.__dict__['effective_exposure_type']
        # Fall back to property if no annotation exists
        return obj.effective_exposure_type

    @extend_schema_field(OpenApiTypes.STR)
    def get_effective_exposure_type_display(self, obj) -> Optional[str]:
        return obj.get_effective_exposure_type_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_exposure_type_ml_display(self, obj) -> Optional[str]:
        if obj.exposure_type_ml:
            # Get display value from choices
            for code, label in DataFile.EXPOSURE_TYPE_POSSIBILITIES:
                if code == obj.exposure_type_ml:
                    return label
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_exposure_type_user_display(self, obj) -> Optional[str]:
        if obj.exposure_type_user:
            # Get display value from choices
            for code, label in DataFile.EXPOSURE_TYPE_POSSIBILITIES:
                if code == obj.exposure_type_user:
                    return label
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_binning(self, obj) -> str:
        try:
            header = obj.get_fits_header()
            bx = header.get('XBINNING') or header.get('XBIN') or header.get('BINX')
            by = header.get('YBINNING') or header.get('YBIN') or header.get('BINY')
            if (bx is None or by is None) and header.get('BINNING'):
                import re
                parts = [p for p in re.split(r"[^0-9]+", str(header.get('BINNING'))) if p]
                if len(parts) >= 2:
                    bx = parts[0]
                    by = parts[1]
            bx = int(str(bx)) if bx is not None else 1
            by = int(str(by)) if by is not None else 1
            return f"{bx}x{by}"
        except Exception:
            return "1x1"

    @extend_schema_field(OpenApiTypes.STR)
    def get_observation_run_name(self, obj) -> str:
        return obj.observation_run.name

    @extend_schema_field({'type': 'array', 'items': {'type': 'integer'}})
    def get_object_ids(self, obj) -> list[int]:
        """List of object PKs this datafile is associated with."""
        objs = obj.object_set.all().only('pk')
        return [o.pk for o in objs]

    @extend_schema_field(OpenApiTypes.INT)
    def get_main_object_id(self, obj) -> Optional[int]:
        """
        Object ID for linking when displaying main_target.
        Prefer object whose name matches main_target; else first object if only one.
        """
        objs = list(obj.object_set.all().only('pk', 'name'))
        if not objs:
            return None
        main_target = (obj.main_target or '').strip()
        if main_target:
            for o in objs:
                if o.name and str(o.name).strip().lower() == main_target.lower():
                    return o.pk
        if len(objs) == 1:
            return objs[0].pk
        return objs[0].pk if objs else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_main_object_name(self, obj) -> Optional[str]:
        """Name of the object we link to (main_object_id)."""
        objs = list(obj.object_set.all().only('pk', 'name'))
        if not objs:
            return None
        main_target = (obj.main_target or '').strip()
        if main_target:
            for o in objs:
                if o.name and str(o.name).strip().lower() == main_target.lower():
                    return o.name
        if len(objs) == 1:
            return objs[0].name
        return objs[0].name if objs else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_ra_hms(self, obj) -> str:
        return obj.ra_hms()

    @extend_schema_field(OpenApiTypes.STR)
    def get_dec_dms(self, obj) -> str:
        return obj.dec_dms()

    def update(self, instance, validated_data):
        """Override update to set override flags for user changes."""
        from obs_run.utils import check_and_set_override, get_override_field_name
        
        # Track changes and set override flags
        override_fields = []
        fields_to_check = ['exposure_type', 'spectroscopy', 'spectrograph', 
                          'instrument', 'telescope', 'status_parameters']
        
        for field_name in fields_to_check:
            if field_name in validated_data:
                old_value = getattr(instance, field_name, None)
                new_value = validated_data[field_name]
                if check_and_set_override(instance, field_name, new_value, old_value):
                    override_fields.append(get_override_field_name(field_name))
        
        # Perform the update
        instance = super().update(instance, validated_data)
        
        # Save override flags if any were set
        if override_fields:
            instance.save(update_fields=override_fields)
        
        return instance

    # Override to_representation to normalize instrument/telescope aliases
    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            if 'instrument' in data and data['instrument']:
                data['instrument'] = normalize_alias(data['instrument'], INSTRUMENT_ALIASES)
        except Exception:
            pass
        try:
            if 'telescope' in data and data['telescope']:
                data['telescope'] = normalize_alias(data['telescope'], TELESCOPE_ALIASES)
        except Exception:
            pass
        return data
