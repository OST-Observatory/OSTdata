"""Shared OpenAPI helpers for drf-spectacular (named schemas, JSON object responses)."""
from drf_spectacular.types import OpenApiTypes
from rest_framework import serializers


class EmptyObjectSerializer(serializers.Serializer):
    """Named empty serializer so schema components are never anonymous."""


class GenericJSONObjectSerializer(serializers.Serializer):
    """Opaque JSON object response/request body for free-form admin/API endpoints."""

    class Meta:
        ref_name = 'GenericJSONObject'


# Common response shortcuts for @extend_schema
JSON_OBJECT = OpenApiTypes.OBJECT
JSON_OBJECT_RESPONSE = {200: OpenApiTypes.OBJECT}
JSON_OBJECT_ACCEPTED = {202: OpenApiTypes.OBJECT}
