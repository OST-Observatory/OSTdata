from django.urls import reverse

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
    IntegerField,
)

from objects.models import Object
from tags.models import Tag
from tags.api.serializers import TagSerializer
from obs_run.api.serializers import RunSerializer

# ===============================================================
#   OBJECTS
# ===============================================================

class ObjectListSerializer(ModelSerializer):

    observation_run = SerializerMethodField()
    tags = SerializerMethodField()
    href = SerializerMethodField()
    object_type_display = SerializerMethodField()
    last_modified = SerializerMethodField()
    tag_ids = PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        read_only=False,
        source='tags',
    )

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
            'href',
            'is_main',
            'ra_hms',
            'dec_dms',
            'object_type_display',
            'last_modified',
            # 'simbad_resolved',
        ]
        read_only_fields = ('pk',)


    def get_observation_run(self, obj):
        observation_runs = RunSerializer(obj.observation_run, many=True).data
        return observation_runs

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_href(self, obj):
        return reverse('objects:object_detail', args=[obj.pk])

    def get_object_type_display(self, obj):
        return obj.get_object_type_display()

    def get_last_modified(self, obj):
        history = obj.history.order_by('-history_date').first()
        return history.history_date if history else None

