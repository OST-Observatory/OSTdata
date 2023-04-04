from rest_framework import viewsets
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from objects.models import Object

from .serializers import ObjectListSerializer

from obs_run.api.serializers import RunListSerializer

from .filter import ObjectFilter

# ===============================================================
#   OBJECTS
# ===============================================================

class ObjectViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all objects in the database
    """

    queryset = Object.objects.all()
    serializer_class = ObjectListSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_class = ObjectFilter


class getObjectRunViewSet(viewsets.ModelViewSet):
    """
    A ViewSet to get all Observation runs associated with an Object
    """
    queryset = Object.objects.all()
    serializer_class = RunListSerializer

    def list(self, request, object_pk):
        queryset = Object.objects.get(pk=object_pk).obsrun.all()
        serializer = RunListSerializer(queryset, many=True)
        return Response(serializer.data)
