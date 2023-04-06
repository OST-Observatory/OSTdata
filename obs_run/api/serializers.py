
from django.urls import reverse

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
    ReadOnlyField,
)

from pathlib import Path

from obs_run.models import Obs_run, DataFile
from tags.models import Tag
from tags.api.serializers import TagSerializer
from objects.api.simple_serializers import ObjectSimpleSerializer

# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunListSerializer(ModelSerializer):

    tags = SerializerMethodField()
    href = SerializerMethodField()
    reduction_status_display = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )
    n_datafiles =  SerializerMethodField()
    n_fits =  SerializerMethodField()
    n_img =  SerializerMethodField()
    n_ser =  SerializerMethodField()
    expo_time = SerializerMethodField()
    start_time = SerializerMethodField()
    end_time = SerializerMethodField()
    objects = SerializerMethodField()

    class Meta:
        model = Obs_run
        fields = [
            'pk',
            'name',
            'reduction_status',
            'reduction_status_display',
            'tags',
            'tag_ids',
            'href',
            'n_datafiles',
            'n_fits',
            'n_img',
            'n_ser',
            'expo_time',
            'start_time',
            'end_time',
            'photometry',
            'spectroscopy',
            'objects',
        ]
        read_only_fields = ('pk',)

        datatables_always_serialize = ('href','pk')

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_href(self, obj):
        return reverse('obs_runs:run_detail', args=[obj.pk])

    def get_reduction_status_display(self, obj):
        return obj.get_reduction_status_display()

    def get_n_datafiles(self, obj):
        datafiles = obj.datafile_set.all()
        return len(datafiles)

    def get_n_fits(self, obj):
        fits = obj.datafile_set.filter(file_type__exact='FITS')
        return len(fits)

    def get_n_img(self, obj):
        jpegs = obj.datafile_set.filter(file_type__exact='JPG')
        cr2s = obj.datafile_set.filter(file_type__exact='CR2')
        return len(jpegs) + len(cr2s)

    def get_n_ser(self, obj):
        sers = obj.datafile_set.filter(file_type__exact='SER')
        return len(sers)

    def get_expo_time(self, obj):
        data_files = obj.datafile_set.all()

        total_expo_time = 0
        for f in data_files:
            expo_time = f.exptime
            if expo_time > 0:
                total_expo_time += expo_time

        return total_expo_time

    def get_start_time(self, obj):
        #   Filter JD to avoid files with the default date (2000:01:01 00:00:00)
        data_files = obj.datafile_set.filter(hjd__gt=2451545).order_by('hjd')
        if len(data_files) > 0:
            return data_files[0].obs_date
        else:
            return '2000-01-01 00:00:00'

    def get_end_time(self, obj):
        # data_files = obj.datafile_set.all().order_by('hjd').reverse()
        data_files = obj.datafile_set.filter(
            hjd__gt=2451545
            ).order_by('hjd').reverse()
        if len(data_files) > 0:
            return data_files[0].obs_date
        else:
            return '2000-01-01 00:00:00'


    def get_objects(self, obj):
        objects = ObjectSimpleSerializer(obj.object_set.all(), many=True).data
        return objects

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
    n_fits =  SerializerMethodField()
    n_img =  SerializerMethodField()
    n_ser =  SerializerMethodField()
    expo_time = SerializerMethodField()

    owner = ReadOnlyField(source='added_by.username')

    class Meta:
        model = Obs_run
        fields = [
            'pk',
            'name',
            'reduction_status',
            'reduction_status_display',
            'note',
            'tags',
            'tag_ids',
            'href',
            'owner',
            'n_fits',
            'n_img',
            'n_ser',
            'expo_time',
        ]
        read_only_fields = ('pk', 'tags', 'reduction_status_display')


    def get_href(self, obj):
        return reverse('obs_runs:run_detail', args=[obj.pk])

    def get_tags(self, obj):
        #   This has to be used instead of a through field, as otherwise
        #   PUT or PATCH requests fail!
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_reduction_status_display(self, obj):
        return obj.get_reduction_status_display()

    def get_n_fits(self, obj):
        fits = obj.datafile_set.filter(file_type__exact='FITS')
        return len(fits)

    def get_n_img(self, obj):
        jpegs = obj.datafile_set.filter(file_type__exact='JPG')
        cr2s = obj.datafile_set.filter(file_type__exact='CR2')
        return len(jpegs) + len(cr2s)

    def get_n_ser(self, obj):
        sers = obj.datafile_set.filter(file_type__exact='SER')
        return len(sers)

    def get_expo_time(self, obj):
        data_files = obj.datafile_set.all()

        total_expo_time = 0
        for f in data_files:
            expo_time = f.exptime
            if expo_time > 0:
                total_expo_time += expo_time

        return total_expo_time

################################################################################

class SimpleRunSerializer(ModelSerializer):
   """
   Basic serializer only returning the most basic information
   available for the Obs_run object
   """

   href = SerializerMethodField()

   class Meta:
      model = Obs_run
      fields = [
            'pk',
            'name',
            'href',
      ]
      read_only_fields = ('pk',)

   def get_href(self, obj):
      return reverse('runs:run_detail', args=[obj.pk])


# ===============================================================
#   DATA FILE
# ===============================================================

class DataFileSerializer(ModelSerializer):

    tags = SerializerMethodField()
    exposure_type_display = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )
    file_path = SerializerMethodField()
    file_name = SerializerMethodField()

    class Meta:
        model = DataFile
        fields = [
            'pk',
            'obsrun',
            'file_path',
            'file_name',
            'file_type',
            'exposure_type',
            'exposure_type_display',
            'tags',
            'tag_ids',
            'added_by',
            'hjd',
            'obs_date',
            'exptime',
            'naxis1',
            'naxis2',
            'main_target',
            'ra',
            'dec',
            'ra_hms',
            'dec_dms',
        ]
        read_only_fields = ('pk', 'added_by')


    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_file_path(self, obj):
        return obj.datafile

    def get_file_name(self, obj):
        path = Path(obj.datafile)
        return path.name

    def get_exposure_type_display(self, obj):
        return obj.get_exposure_type_display()
