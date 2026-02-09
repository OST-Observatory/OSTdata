from django.urls import reverse
from django.utils import timezone

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
    ReadOnlyField,
)

from pathlib import Path

from obs_run.models import ObservationRun, DataFile
from tags.models import Tag
from tags.api.serializers import TagSerializer
from objects.api.simple_serializers import ObjectSimpleSerializer
from obs_run.utils import normalize_alias, INSTRUMENT_ALIASES, TELESCOPE_ALIASES


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
    start_time = SerializerMethodField()
    end_time = SerializerMethodField()
    objects = SerializerMethodField()

    owner = ReadOnlyField(source='added_by.username')

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
            'start_time',
            'end_time',
            'objects',
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
        read_only_fields = ('pk', 'tags', 'reduction_status_display')
    
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

    def get_href(self, obj):
        # Return SPA route instead of Django reverse (legacy templates removed)
        return f"/observation-runs/{obj.pk}"

    def get_tags(self, obj):
        #   This has to be used instead of a through field, as otherwise
        #   PUT or PATCH requests fail!
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_reduction_status_display(self, obj):
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

    def get_n_datafiles(self, obj):
        return self._get_annotated_or(obj, 'n_datafiles', lambda: obj.datafile_set.count())

    def get_n_fits(self, obj):
        return self._get_annotated_or(
            obj,
            'n_fits',
            lambda: obj.datafile_set.filter(file_type__exact='FITS').count(),
        )

    def get_n_img(self, obj):
        return self._get_annotated_or(
            obj,
            'n_img',
            lambda: (
                obj.datafile_set.filter(file_type__exact='JPG').count()
                + obj.datafile_set.filter(file_type__exact='CR2').count()
                + obj.datafile_set.filter(file_type__exact='TIFF').count()
            ),
        )

    def get_n_ser(self, obj):
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

    def get_n_light(self, obj):
        return self._count_exptype(obj, {'ann': 'n_light', 'codes': ['LI'], 'prefixes': ['LIGHT']})

    def get_n_flat(self, obj):
        return self._count_exptype(obj, {'ann': 'n_flat', 'codes': ['FL'], 'prefixes': ['FLAT']})

    def get_n_dark(self, obj):
        return self._count_exptype(obj, {'ann': 'n_dark', 'codes': ['DA'], 'prefixes': ['DARK']})

    # (legacy alias getters removed)

    def get_expo_time(self, obj):
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

    def get_start_time(self, obj):
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

    def get_end_time(self, obj):
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

    def get_objects(self, obj):
        objects = ObjectSimpleSerializer(obj.object_set.all(), many=True).data
        return objects


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

    def get_href(self, obj):
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
    file_path = SerializerMethodField()
    file_name = SerializerMethodField()
    observation_run_name = SerializerMethodField()

    class Meta:
        model = DataFile
        fields = [
            'pk',
            'observation_run',
            'observation_run_name',
            'file_path',
            'file_name',
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
            'hjd',
            'obs_date',
            'exptime',
            'naxis1',
            'naxis2',
            'main_target',
            'header_target_name',
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
        ]
        # read_only_fields = ('pk', 'added_by')
        read_only_fields = ('pk',)
    
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

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_file_path(self, obj):
        return obj.datafile

    def get_file_name(self, obj):
        path = Path(obj.datafile)
        return path.name

    def get_exposure_type_display(self, obj):
        # Return effective exposure type display instead of raw exposure_type
        return obj.get_effective_exposure_type_display()

    def get_effective_exposure_type(self, obj):
        return obj.effective_exposure_type

    def get_effective_exposure_type_display(self, obj):
        return obj.get_effective_exposure_type_display()

    def get_exposure_type_ml_display(self, obj):
        if obj.exposure_type_ml:
            # Get display value from choices
            for code, label in DataFile.EXPOSURE_TYPE_POSSIBILITIES:
                if code == obj.exposure_type_ml:
                    return label
        return None

    def get_exposure_type_user_display(self, obj):
        if obj.exposure_type_user:
            # Get display value from choices
            for code, label in DataFile.EXPOSURE_TYPE_POSSIBILITIES:
                if code == obj.exposure_type_user:
                    return label
        return None

    def get_binning(self, obj):
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

    def get_observation_run_name(self, obj):
        return obj.observation_run.name

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
