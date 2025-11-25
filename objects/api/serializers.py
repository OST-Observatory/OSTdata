from django.urls import reverse
from django.utils import timezone

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
    IntegerField,
)

from objects.models import Object
from tags.models import Tag
from tags.api.serializers import TagSerializer

# ===============================================================
#   OBJECTS
# ===============================================================

# Simple alias maps to normalize common instrument/telescope names
INSTRUMENT_ALIASES = {
    'sbig st-8 3 ccd camera': 'ST-8',
    'sbig st-8': 'ST-8',
    'sbig st8': 'ST-8',
    'st-8': 'ST-8',
    'st8': 'ST-8',
    'QHYCCD-Cameras-Capture': 'QHY600M or QHY268M',
    'QHY600M': 'QHY600M',
    'QHY268M': 'QHY268M',
    'QHY600': 'QHY600M',
    'QHY268': 'QHY268M',
    'SBIG ST-i CCD Camera': 'ST-i',
    'SBIG ST-i': 'ST-i',
    'SBIG ST-i CCD': 'ST-i',
    'SBIG ST-i CCD Camera': 'ST-i',
    'SBIG ST-i CCD Camera': 'ST-i',
}

TELESCOPE_ALIASES = {
    'meade lx200': 'LX200',
    'lx200': 'LX200',
    'sky-watcher': 'SkyWatcher',
    'Planewave CDK20': 'CDK20',
}


# Normalize alias maps to lowercase keys for robust, case-insensitive lookup
INSTRUMENT_ALIASES = { (k.strip().lower() if isinstance(k, str) else k): v for k, v in INSTRUMENT_ALIASES.items() }
TELESCOPE_ALIASES  = { (k.strip().lower() if isinstance(k, str) else k): v for k, v in TELESCOPE_ALIASES.items() }


def normalize_alias(name: str, aliases: dict) -> str:
    if not name:
        return name
    key = str(name).strip().lower()
    return aliases.get(key, name)


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
        ]
        read_only_fields = ('pk',)


    def get_observation_run(self, obj):
        runs = obj.observation_run.all()
        result = []
        for run in runs:
            # DataFiles linked to this object within this run
            df_qs = obj.datafiles.filter(observation_run=run)
            df_science = df_qs.filter(exposure_type='LI')

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
            except Exception:
                n_fits = n_img = n_ser = 0

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

            # Observed start/end from science frames with valid HJD
            try:
                valid = df_science.filter(hjd__gt=2451545).order_by('hjd')
                observed_start = None
                observed_end = None
                if valid.exists():
                    s = valid.first().obs_date
                    e = valid.last().obs_date
                    try:
                        if s is not None:
                            if timezone.is_naive(s):
                                s = timezone.make_aware(s, timezone.get_current_timezone())
                            observed_start = s.isoformat()
                        if e is not None:
                            if timezone.is_naive(e):
                                e = timezone.make_aware(e, timezone.get_current_timezone())
                            observed_end = e.isoformat()
                    except Exception:
                        observed_start = None
                        observed_end = None
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
                'instruments': instruments,
                'telescopes': telescopes,
                'airmass_min': airmass_min,
                'airmass_max': airmass_max,
                'observed_start': observed_start,
                'observed_end': observed_end,
            })
        return result

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_identifiers(self, obj):
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

    def get_href(self, obj):
        # SPA route to object detail
        return f"/objects/{obj.pk}"

    def get_object_type_display(self, obj):
        return obj.get_object_type_display()

    def get_last_modified(self, obj):
        history = obj.history.order_by('-history_date').first()
        return history.history_date if history else None

    def get_ra_hms(self, obj):
        return obj.ra_hms()

    def get_dec_dms(self, obj):
        return obj.dec_dms()

    def get_n_light(self, obj):
        try:
            return obj.datafiles.filter(exposure_type='LI').count()
        except Exception:
            return 0

    def get_light_expo_time(self, obj):
        try:
            total = 0
            for f in obj.datafiles.filter(exposure_type='LI').only('exptime'):
                try:
                    if getattr(f, 'exptime', 0) and f.exptime > 0:
                        total += f.exptime
                except Exception:
                    continue
            return total
        except Exception:
            return 0

