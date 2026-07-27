from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
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

    @extend_schema_field(OpenApiTypes.STR)
    def get_href(self, obj) -> str:
        # Return SPA route to object detail
        return f"/objects/{obj.pk}"
