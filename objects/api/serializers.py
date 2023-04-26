from django.urls import reverse

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
    PrimaryKeyRelatedField,
)

from objects.models import Object
from tags.models import Tag
from tags.api.serializers import TagSerializer
from obs_run.api.serializers import RunSerializer

# ===============================================================
#   OBJECTS
# ===============================================================

class ObjectListSerializer(ModelSerializer):

    obsrun = SerializerMethodField()
    tags = SerializerMethodField()
    href = SerializerMethodField()
    object_type_display = SerializerMethodField()
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
            'obsrun',
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
            # 'simbad_resolved',
        ]
        read_only_fields = ('pk',)


    def get_obsrun(self, obj):
        obsruns = RunSerializer(obj.obsrun, many=True).data
        return obsruns

    def get_tags(self, obj):
        tags = TagSerializer(obj.tags, many=True).data
        return tags

    def get_href(self, obj):
        return reverse('objects:object_detail', args=[obj.pk])

    def get_object_type_display(self, obj):
        return obj.get_object_type_display()
