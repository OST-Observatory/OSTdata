from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import OrderingFilter

from django_filters.rest_framework import DjangoFilterBackend

from objects.models import Object
from django.db import models

from .serializers import ObjectListSerializer

from obs_run.api.serializers import RunListSerializer, DataFileSerializer

from .filter import ObjectFilter

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from astropy.coordinates import SkyCoord
import astropy.units as u

# ===============================================================
#   OBJECTS
# ===============================================================

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 100

    def get_page_size(self, request):
        if self.page_size_query_param:
            try:
                page_size = int(request.query_params[self.page_size_query_param])
                if page_size == -1:
                    return 10000  # Use a large number instead of None
                return min(page_size, self.max_page_size)
            except (KeyError, ValueError):
                pass
        return self.page_size

    def paginate_queryset(self, queryset, request, view=None):
        page_size = self.get_page_size(request)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return super().get_paginated_response(data)

class ObjectViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all objects in the database
    """

    queryset = Object.objects.all()
    serializer_class = ObjectListSerializer
    pagination_class = StandardResultsSetPagination

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ObjectFilter
    ordering_fields = ['name', 'object_type', 'ra', 'dec']
    ordering = ['name']  # default ordering

    def get_queryset(self):
        queryset = super().get_queryset()
        ordering = self.request.query_params.get('ordering', '')
        
        # Handle last_modified sorting using history
        if ordering == 'last_modified':
            return queryset.annotate(
                last_modified=models.Subquery(
                    Object.history.filter(
                        id=models.OuterRef('id')
                    ).order_by('-history_date').values('history_date')[:1]
                )
            ).order_by('last_modified')
        elif ordering == '-last_modified':
            return queryset.annotate(
                last_modified=models.Subquery(
                    Object.history.filter(
                        id=models.OuterRef('id')
                    ).order_by('-history_date').values('history_date')[:1]
                )
            ).order_by('-last_modified')
            
        return queryset

class getObjectRunViewSet(viewsets.ModelViewSet):
    """
    A ViewSet to get all Observation runs associated with an Object
    """
    queryset = Object.objects.all()
    serializer_class = RunListSerializer

    def list(self, request, object_pk):
        queryset = Object.objects.get(pk=object_pk).observation_run.all()
        serializer = RunListSerializer(queryset, many=True)
        return Response(serializer.data)


class getObjectDatafileViewSet(viewsets.ModelViewSet):
    """
    A ViewSet to get all data files associated with an Object
    """
    queryset = Object.objects.all()
    serializer_class = DataFileSerializer

    def list(self, request, object_pk):
        queryset = Object.objects.get(pk=object_pk).datafiles.all()
        serializer = DataFileSerializer(queryset, many=True)
        return Response(serializer.data)

class VuetifyDataTablePagination(PageNumberPagination):
    """
    Custom pagination class specifically designed for v-data-table
    """
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 1000

    def get_page_size(self, request):
        if self.page_size_query_param:
            try:
                page_size = int(request.query_params[self.page_size_query_param])
                if page_size == -1:  # Handle "All" option
                    return 10000  # Return a large number to get all items
                return min(page_size, self.max_page_size)
            except (KeyError, ValueError):
                pass
        return self.page_size

    def paginate_queryset(self, queryset, request, view=None):
        self.page_size = self.get_page_size(request)
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        return Response({
            'items': data,
            'total': self.page.paginator.count,
            'page': self.page.number,
            'pageCount': self.page.paginator.num_pages,
            'itemsPerPage': self.page_size
        })

class ObjectVuetifyViewSet(viewsets.ModelViewSet):
    """
    ViewSet specifically designed for v-data-table integration
    """
    queryset = Object.objects.all()
    serializer_class = ObjectListSerializer
    pagination_class = VuetifyDataTablePagination
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ObjectFilter
    ordering_fields = ['name', 'object_type', 'ra', 'dec']
    ordering = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Handle search parameter
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        # Handle object type filter
        object_type = self.request.query_params.get('object_type', None)
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        
        # Handle observation run filter
        observation_run = self.request.query_params.get('observation_run', None)
        if observation_run:
            queryset = queryset.filter(observation_run__pk=observation_run)
        
        # Handle coordinate filter using astropy
        ra = self.request.query_params.get('ra', None)
        dec = self.request.query_params.get('dec', None)
        radius = self.request.query_params.get('radius', None)
        if ra and dec and radius:
            try:
                target = SkyCoord(float(ra), float(dec), unit='deg')
                radius_arcsec = float(radius)
                filtered_ids = []
                for obj in queryset:
                    if obj.ra == -1 or obj.dec == -1:
                        continue
                    obj_coord = SkyCoord(obj.ra, obj.dec, unit='deg')
                    sep = target.separation(obj_coord)
                    if sep.arcsecond <= radius_arcsec:
                        filtered_ids.append(obj.pk)
                if filtered_ids:
                    queryset = queryset.filter(pk__in=filtered_ids)
                else:
                    queryset = queryset.none()
            except Exception as e:
                queryset = queryset.none()
        
        # Handle sorting
        sort_by = self.request.query_params.get('sortBy', None)
        sort_desc = self.request.query_params.get('sortDesc', 'false')
        
        if sort_by:
            # Remove any leading '-' as we handle the direction separately
            sort_field = sort_by.lstrip('-')
            if sort_desc.lower() == 'true' or sort_by.startswith('-'):
                sort_field = f'-{sort_field}'
            queryset = queryset.order_by(sort_field)
        
        return queryset.distinct()  # Ensure we don't get duplicate objects

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
