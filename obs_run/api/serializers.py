
from django.urls import reverse

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
    ReadOnlyField,
)

from obs_run.models import Obs_run
from tags.models import Tag
#from tags.api.serializers import SimpleTagSerializer, TagSerializer
from tags.api.serializers import TagSerializer

# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunListSerializer(ModelSerializer):

    tags = SerializerMethodField()
    #datasets = SerializerMethodField()
    href = SerializerMethodField()
    reduction_status_display = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )

    class Meta:
        model = Obs_run
        fields = [
            'pk',
            'name',
            'reduction_status',
            'reduction_status_display',
            'note',
            'tags',
            #'datasets',
            'tag_ids',
            'href',
            'added_by',
        ]
        read_only_fields = ('pk', 'added_by')

        datatables_always_serialize = ('href','pk')

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    #def get_datasets(self, obj):
        #try:
            #datasets = obj.dataset_set.all()
            #return [{'name':d.name, 'color':d.method.color, 'href':reverse('analysis:dataset_detail', kwargs={'project':d.project.slug, 'dataset_id':d.pk})} for d in datasets]
        #except Exception as e:
            #print (e)
            #return []

    def get_href(self, obj):
        return reverse('runs:run_detail', args=[obj.pk])

    def get_reduction_status_display(self, obj):
        return obj.get_reduction_status_display()

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
        ]
        read_only_fields = ('pk', 'tags', 'reduction_status_display')


    def get_tags(self, obj):
        #   This has to be used instead of a through field, as otherwise
        #   PUT or PATCH requests fail!
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_href(self, obj):
        return reverse('runs:run_detail', args=[obj.pk])

    def get_reduction_status_display(self, obj):
        return obj.get_reduction_status_display()

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
