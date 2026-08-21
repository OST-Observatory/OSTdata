from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework.serializers import (
    ModelSerializer,
    PrimaryKeyRelatedField,
    SerializerMethodField,
)

from objects.models import Object
from objects.search import find_search_match_via
from objects.solar_system_images import image_info_for_object
from obs_run.utils import INSTRUMENT_ALIASES, TELESCOPE_ALIASES, normalize_alias
from tags.api.serializers import TagSerializer
from tags.models import Tag

# ===============================================================
#   OBJECTS
# ===============================================================


class ObjectListSerializer(ModelSerializer):

    observation_run = SerializerMethodField()
    tags = SerializerMethodField()
    href = SerializerMethodField()
    object_type_display = SerializerMethodField()
    last_modified = SerializerMethodField()
    ra_hms = SerializerMethodField()
    dec_dms = SerializerMethodField()
    n_light = SerializerMethodField()
    light_expo_time = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )
    identifiers = SerializerMethodField()
    has_solar_system_image = SerializerMethodField()
    solar_system_image_url = SerializerMethodField()
    search_match_via = SerializerMethodField()

    class Meta:
        model = Object
        fields = [
            'pk',
            'observation_run',
            'name',
            'ra',
            'dec',
            'tags',
            'tag_ids',
            'identifiers',
            'href',
            'is_main',
            'ra_hms',
            'dec_dms',
            'object_type_display',
            'last_modified',
            'simbad_resolved',
            'spectroscopy',
            'photometry',
            'n_light',
            'light_expo_time',
            'note',
            'is_public',
            'object_type',
            'first_hjd',
            # Override flags (read-only for normal users, editable for admins)
            'name_override',
            'is_public_override',
            'ra_override',
            'dec_override',
            'first_hjd_override',
            'is_main_override',
            'photometry_override',
            'spectroscopy_override',
            'simbad_resolved_override',
            'object_type_override',
            'note_override',
            'exclude_from_orphan_cleanup',
            'has_solar_system_image',
            'solar_system_image_url',
            'search_match_via',
        ]
        read_only_fields = ('pk',)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make override flags read-only for non-admin users
        request = self.context.get('request')
        if request and not (
            request.user.is_superuser
            or request.user.has_perm('users.acl_object_admin_edit')
        ):
            for field_name in ['name_override', 'is_public_override', 'ra_override', 'dec_override',
                             'first_hjd_override', 'is_main_override', 'photometry_override',
                             'spectroscopy_override', 'simbad_resolved_override', 'object_type_override',
                             'note_override', 'exclude_from_orphan_cleanup']:
                if field_name in self.fields:
                    self.fields[field_name].read_only = True


    @extend_schema_field(OpenApiTypes.STR)
    def get_search_match_via(self, obj) -> Optional[str]:
        search = self.context.get('search')
        if not search:
            return None
        return find_search_match_via(obj, search)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_solar_system_image(self, obj) -> bool:
        if getattr(obj, 'object_type', None) != 'SO':
            return False
        has_image, _, _ = image_info_for_object(obj, self.context.get('request'))
        return has_image

    @extend_schema_field(OpenApiTypes.URI)
    def get_solar_system_image_url(self, obj) -> Optional[str]:
        if getattr(obj, 'object_type', None) != 'SO':
            return None
        has_image, url, _ = image_info_for_object(obj, self.context.get('request'))
        return url if has_image else None

    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_observation_run(self, obj) -> list[dict[str, Any]]:
        runs = obj.observation_run.all()
        result = []
        for run in runs:
            # DataFiles linked to this object within this run
            df_qs = obj.datafiles.filter(observation_run=run)
            # Use effective exposure type for filtering
            from utilities import annotate_effective_exposure_type
            df_qs = annotate_effective_exposure_type(df_qs)
            df_science = df_qs.filter(annotated_effective_exposure_type='LI')
            try:
                n_total = df_qs.count()
            except Exception:
                n_total = 0

            # Exposure time (sum of positive exptimes) on science frames
            expo_time = 0
            try:
                for f in df_science:
                    if getattr(f, 'exptime', 0) and f.exptime > 0:
                        expo_time += f.exptime
            except Exception:
                expo_time = 0

            # Counts by file type (all files in this run for the object)
            try:
                n_fits = df_qs.filter(file_type__exact='FITS').count()
                n_img = (
                    df_qs.filter(file_type__exact='JPG').count()
                    + df_qs.filter(file_type__exact='CR2').count()
                    + df_qs.filter(file_type__exact='TIFF').count()
                )
                n_ser = df_qs.filter(file_type__exact='SER').count()
                n_flat = df_qs.filter(annotated_effective_exposure_type='FL').count()
                n_dark = df_qs.filter(annotated_effective_exposure_type='DA').count()
            except Exception:
                n_fits = n_img = n_ser = n_flat = n_dark = 0

            # Instruments & Telescopes (unique, non-empty) with alias normalization
            try:
                instruments_raw = [x for x in df_qs.values_list('instrument', flat=True) if x]
                telescopes_raw = [x for x in df_qs.values_list('telescope', flat=True) if x]
                instruments = list({ normalize_alias(x, INSTRUMENT_ALIASES) for x in instruments_raw })
                telescopes = list({ normalize_alias(x, TELESCOPE_ALIASES) for x in telescopes_raw })
            except Exception:
                instruments = []
                telescopes = []

            # Airmass range from science frames
            airmass_min = None
            airmass_max = None
            try:
                airmasses = [am for am in df_science.values_list('air_mass', flat=True) if am is not None and am > 0]
                if airmasses:
                    airmass_min = min(airmasses)
                    airmass_max = max(airmasses)
            except Exception:
                pass

            # Observed start/end from science frames with valid HJD.
            # Note: DataFile.obs_date is a CharField (string), not a datetime. Provide ISO-like strings.
            try:
                valid = df_science.filter(hjd__gt=2451545).order_by('hjd')
                observed_start = None  # string like "YYYY-MM-DD HH:MM:SS" or ISO
                observed_end = None
                if valid.exists():
                    s = valid.first().obs_date
                    e = valid.last().obs_date
                    def _normalize_obs_date(val):
                        # Accept datetime or string; normalize to ISO-like string compatible with frontend parser
                        try:
                            # datetime instance
                            from datetime import datetime
                            if isinstance(val, datetime):
                                # Ensure aware in current timezone for isoformat consistency
                                if timezone.is_naive(val):
                                    val = timezone.make_aware(val, timezone.get_current_timezone())
                                return val.isoformat()
                        except Exception:
                            pass
                        # Fallback: string normalization
                        try:
                            s = str(val).strip()
                            if not s:
                                return None
                            # Convert "YYYY-MM-DD HH:MM:SS" -> "YYYY-MM-DDTHH:MM:SSZ" for unambiguous UTC parse on UI
                            if 'T' not in s and ' ' in s:
                                s = s.replace(' ', 'T')
                            if 'Z' not in s and '+' not in s:
                                s = s + 'Z'
                            return s
                        except Exception:
                            return None
                    observed_start = _normalize_obs_date(s)
                    observed_end = _normalize_obs_date(e)
            except Exception:
                observed_start = None
                observed_end = None

            result.append({
                'pk': run.pk,
                'name': run.name,
                # SPA route to run detail
                'href': f"/observation-runs/{run.pk}",
                'reduction_status': run.reduction_status,
                'reduction_status_display': run.get_reduction_status_display(),
                'n_light': df_science.count(),
                'expo_time': expo_time,
                'n_fits': n_fits,
                'n_img': n_img,
                'n_ser': n_ser,
                'n_flat': n_flat,
                'n_dark': n_dark,
                'n_total': n_total,
                'instruments': instruments,
                'telescopes': telescopes,
                'airmass_min': airmass_min,
                'airmass_max': airmass_max,
                'observed_start': observed_start,
                'observed_end': observed_end,
            })
        return result

    @extend_schema_field(TagSerializer(many=True))
    def get_tags(self, obj) -> list:
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    @extend_schema_field({'type': 'array', 'items': {'type': 'object'}})
    def get_identifiers(self, obj) -> list[dict[str, Any]]:
        try:
            items = obj.identifier_set.all()
            out = []
            for it in items:
                out.append({
                    'pk': getattr(it, 'pk', None),
                    'name': getattr(it, 'name', None),
                    'href': getattr(it, 'href', None),
                    'info_from_header': getattr(it, 'info_from_header', False),
                })
            return out
        except Exception:
            return []

    @extend_schema_field(OpenApiTypes.STR)
    def get_href(self, obj) -> str:
        # SPA route to object detail
        return f"/objects/{obj.pk}"

    @extend_schema_field(OpenApiTypes.STR)
    def get_object_type_display(self, obj) -> str:
        return obj.get_object_type_display()

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_last_modified(self, obj) -> Optional[datetime]:
        history = obj.history.order_by('-history_date').first()
        return history.history_date if history else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_ra_hms(self, obj) -> str:
        return obj.ra_hms()

    @extend_schema_field(OpenApiTypes.STR)
    def get_dec_dms(self, obj) -> str:
        return obj.dec_dms()

    @extend_schema_field(OpenApiTypes.INT)
    def get_n_light(self, obj) -> int:
        try:
            from utilities import annotate_effective_exposure_type
            return annotate_effective_exposure_type(obj.datafiles.all()).filter(annotated_effective_exposure_type='LI').count()
        except Exception:
            return 0

    @extend_schema_field(OpenApiTypes.NUMBER)
    def get_light_expo_time(self, obj) -> float:
        try:
            from utilities import annotate_effective_exposure_type
            total = 0.0
            light_files = annotate_effective_exposure_type(obj.datafiles.all()).filter(annotated_effective_exposure_type='LI')
            for f in light_files.only('exptime'):
                try:
                    if getattr(f, 'exptime', 0) and f.exptime > 0:
                        total += f.exptime
                except Exception:
                    continue
            return total
        except Exception:
            return 0.0

