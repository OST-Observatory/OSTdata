from django.urls import reverse

from rest_framework.serializers import (
    ModelSerializer,
    SerializerMethodField,
)

from objects.models import Object

# ===============================================================
#   OBJECTS
# ===============================================================

class ObjectSimpleSerializer(ModelSerializer):

    href = SerializerMethodField()

    class Meta:
        model = Object
        fields = [
            'pk',
            'name',
            'href',
            'is_main',
        ]
        read_only_fields = ('pk',)

    def get_href(self, obj):
        return reverse('objects:object_detail', args=[obj.pk])
