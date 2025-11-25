from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import OrderingFilter

from django_filters.rest_framework import DjangoFilterBackend

from objects.models import Object, Identifier
from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import Replace
from django.db.models import Count, Q
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.utils.http import http_date

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
    permission_classes = [IsAuthenticatedOrReadOnly]

    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ObjectFilter
    ordering_fields = ['name', 'object_type', 'ra', 'dec']
    ordering = ['name']  # default ordering

    def _has(self, user, codename: str) -> bool:
        try:
            return bool(user and (user.is_superuser or user.has_perm(f'users.{codename}')))
        except Exception:
            return False

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tags', 'observation_run', 'datafiles')
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
        
        # Public-only for anonymous users; for authenticated users without explicit permission, hide private
        user = self.request.user
        if user.is_anonymous:
            return queryset.filter(is_public=True)
        if not self._has(user, 'acl_objects_view_private'):
            return queryset.filter(is_public=True)
        return queryset

    @extend_schema(
        summary='List objects',
        description='Paginated list of objects with filters and ordering.',
        parameters=[
            OpenApiParameter('page', int, OpenApiParameter.QUERY),
            OpenApiParameter('limit', int, OpenApiParameter.QUERY),
            OpenApiParameter('ordering', str, OpenApiParameter.QUERY),
            OpenApiParameter('object_type', str, OpenApiParameter.QUERY),
            OpenApiParameter('photometry', bool, OpenApiParameter.QUERY),
            OpenApiParameter('spectroscopy', bool, OpenApiParameter.QUERY),
        ],
    )
    def list(self, request, *args, **kwargs):
        # Validate 'ordering' param explicitly to avoid invalid field errors
        ordering_param = (request.query_params.get('ordering') or '').strip()
        if ordering_param:
            field = ordering_param.lstrip('-')
            allowed = set(self.ordering_fields or [])
            if field not in allowed and field not in ('last_modified',):
                return Response({'detail': f'Invalid ordering: {field}'}, status=400)
        # Conditional GET headers (ETag/Last-Modified) for the list
        try:
            from django.db.models import Max
            from objects.models import Object as ObjectModel
            latest_hist = ObjectModel.history.aggregate(m=Max('history_date'))['m']
            # Compute queryset and count for signature (after filters)
            queryset = self.filter_queryset(self.get_queryset())
            count = queryset.count()
            sig = f"objects:{count}:{str(latest_hist)}:{hash(request.META.get('QUERY_STRING',''))}"
            etag = f"W/\"{abs(hash(sig))}\""
            if request.META.get('HTTP_IF_NONE_MATCH') == etag:
                return Response(status=304)
        except Exception:
            etag = None
            latest_hist = None
            queryset = None
        # Let DRF handle pagination/serialization
        response = super().list(request, *args, **kwargs)
        try:
            if etag:
                response['ETag'] = etag
            if latest_hist:
                response['Last-Modified'] = http_date(int(latest_hist.timestamp()))
        except Exception:
            pass
        return response
    def get_permissions(self):
        # Use authenticated-or-readonly; enforce ACL in handlers for unsafe ops
        return [IsAuthenticatedOrReadOnly()]

    def create(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_objects_edit'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_objects_edit'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_objects_edit'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_objects_delete'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['POST'], permission_classes=[IsAuthenticated])
    def merge(self, request):
        """Merge multiple objects into a target object.
        Body: { target_id: int, source_ids: [int], combine_tags: bool }
        - Moves datafiles, observation_run links, tags, identifiers to target
        - Deletes source objects
        """
        # ACL
        if not self._has(request.user, 'acl_objects_merge'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        payload = request.data if hasattr(request, 'data') else {}
        try:
            target_id = int(payload.get('target_id'))
        except Exception:
            return Response({'detail': 'target_id required'}, status=400)
        src_ids = payload.get('source_ids') or []
        try:
            src_ids = [int(x) for x in src_ids if str(x).strip().isdigit()]
        except Exception:
            src_ids = []
        src_ids = [i for i in src_ids if i != target_id]
        if not src_ids:
            return Response({'merged': 0, 'moved_datafiles': 0, 'moved_runs': 0, 'moved_identifiers': 0, 'moved_tags': 0}, status=200)
        try:
            target = Object.objects.get(pk=target_id)
        except Object.DoesNotExist:
            return Response({'detail': 'target not found'}, status=404)
        combine_tags = bool(payload.get('combine_tags', True))

        moved_df = 0
        moved_runs = 0
        moved_ids = 0
        moved_tags = 0
        removed = 0

        for sid in src_ids:
            try:
                src = Object.objects.get(pk=sid)
            except Object.DoesNotExist:
                continue
            # DataFiles
            try:
                for df in src.datafiles.all().only('pk'):
                    target.datafiles.add(df)
                    moved_df += 1
            except Exception:
                pass
            # Observation runs
            try:
                for run in src.observation_run.all().only('pk'):
                    target.observation_run.add(run)
                    moved_runs += 1
            except Exception:
                pass
            # Identifiers
            try:
                count = Identifier.objects.filter(obj_id=src.pk).update(obj=target)
                moved_ids += int(count or 0)
            except Exception:
                pass
            # Tags
            if combine_tags:
                try:
                    for tag in src.tags.all().only('pk'):
                        target.tags.add(tag)
                        moved_tags += 1
                except Exception:
                    pass
            try:
                src.delete()
                removed += 1
            except Exception:
                pass
        try:
            target.save()
        except Exception:
            pass
        return Response({
            'merged': removed,
            'moved_datafiles': moved_df,
            'moved_runs': moved_runs,
            'moved_identifiers': moved_ids,
            'moved_tags': moved_tags
        }, status=200)

class getObjectRunViewSet(viewsets.ModelViewSet):
    """
    A ViewSet to get all Observation runs associated with an Object
    """
    queryset = Object.objects.all()
    serializer_class = RunListSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def list(self, request, object_pk):
        obj = Object.objects.get(pk=object_pk)
        if request.user.is_anonymous and not obj.is_public:
            return Response({"detail": "Not found"}, status=404)
        queryset = obj.observation_run.all()
        serializer = RunListSerializer(queryset, many=True)
        return Response(serializer.data)


class getObjectDatafileViewSet(viewsets.ModelViewSet):
    """
    A ViewSet to get all data files associated with an Object
    """
    queryset = Object.objects.all()
    serializer_class = DataFileSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def list(self, request, object_pk):
        obj = Object.objects.get(pk=object_pk)
        if request.user.is_anonymous and not obj.is_public:
            return Response({"detail": "Not found"}, status=404)
        queryset = obj.datafiles.all()
        # Optional server-side binning filter from FITS headers
        binning = request.query_params.get('binning')
        if binning:
            try:
                target = str(binning).strip().lower()
                ids = []
                for df in queryset.only('pk'):
                    try:
                        header = df.get_fits_header()
                        bx = header.get('XBINNING') or header.get('XBIN') or header.get('BINX')
                        by = header.get('YBINNING') or header.get('YBIN') or header.get('BINY')
                        if (bx is None or by is None) and header.get('BINNING'):
                            import re
                            parts = [p for p in re.split(r"[^0-9]+", str(header.get('BINNING'))) if p]
                            if len(parts) >= 2:
                                bx = parts[0]
                                by = parts[1]
                        bx = int(str(bx)) if bx is not None else 1
                        by = int(str(by)) if by is not None else 1
                        val = f"{bx}x{by}".lower()
                        if val == target:
                            ids.append(df.pk)
                    except Exception:
                        continue
                queryset = queryset.filter(pk__in=ids)
            except Exception:
                pass
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
    permission_classes = [IsAuthenticatedOrReadOnly]

    def _has(self, user, codename: str) -> bool:
        try:
            return bool(user and (user.is_superuser or user.has_perm(f'users.{codename}')))
        except Exception:
            return False

    def get_queryset(self):
        queryset = super().get_queryset().prefetch_related('tags', 'observation_run', 'datafiles')
        
        # Handle search parameter
        search = self.request.query_params.get('search', None)
        if search:
            try:
                s = str(search).strip()
                # Match either raw name or name without spaces
                queryset = queryset.annotate(name_nospace=Replace('name', Value(' '), Value('')))
                queryset = queryset.filter(Q(name__icontains=s) | Q(name_nospace__icontains=s.replace(' ', '')))
            except Exception:
                queryset = queryset.filter(name__icontains=search)
        
        # Handle object type filter
        object_type = self.request.query_params.get('object_type', None)
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        
        # Handle observation flags (photometry/spectroscopy)
        def parse_bool(val):
            if val is None:
                return None
            s = str(val).strip().lower()
            if s in ('1', 'true', 'yes', 'on'): return True
            if s in ('0', 'false', 'no', 'off'): return False
            return None

        photometry = parse_bool(self.request.query_params.get('photometry', None))
        if photometry is not None:
            queryset = queryset.filter(photometry=photometry)

        spectroscopy = parse_bool(self.request.query_params.get('spectroscopy', None))
        if spectroscopy is not None:
            queryset = queryset.filter(spectroscopy=spectroscopy)

        # Handle observation run filter
        observation_run = self.request.query_params.get('observation_run', None)
        if observation_run:
            queryset = queryset.filter(observation_run__pk=observation_run)
        
        # Handle Lights count filter
        n_light_min = self.request.query_params.get('n_light_min', None)
        n_light_max = self.request.query_params.get('n_light_max', None)
        if n_light_min is not None or n_light_max is not None:
            queryset = queryset.annotate(
                num_li=Count('datafiles', filter=Q(datafiles__exposure_type='LI'))
            )
            try:
                if n_light_min is not None and str(n_light_min).strip() != '':
                    queryset = queryset.filter(num_li__gte=int(n_light_min))
                if n_light_max is not None and str(n_light_max).strip() != '':
                    queryset = queryset.filter(num_li__lte=int(n_light_max))
            except ValueError:
                pass
        
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
        
        # Public-only for anonymous; for authenticated without permission, hide private
        user = self.request.user
        if user.is_anonymous:
            queryset = queryset.filter(is_public=True)
        elif not self._has(user, 'acl_objects_view_private'):
            queryset = queryset.filter(is_public=True)

        return queryset.distinct()  # Ensure we don't get duplicate objects

    def list(self, request, *args, **kwargs):
        # Validate sortBy param
        sort_by = request.query_params.get('sortBy', None)
        if sort_by:
            field = str(sort_by).lstrip('-')
            allowed = set(self.ordering_fields or [])
            if field not in allowed:
                return Response({'detail': f'Invalid sortBy: {field}'}, status=400)
        return super().list(request, *args, **kwargs)

    @extend_schema(summary='Retrieve object', description='Get an object by ID.')
    def retrieve(self, request, *args, **kwargs):
        """Detail with conditional GET headers."""
        instance = self.get_object()
        try:
            hist = instance.history.order_by('-history_date').values_list('history_date', flat=True).first()
        except Exception:
            hist = None
        sig = f"object:{instance.pk}:{str(hist)}"
        etag = f"W/\"{abs(hash(sig))}\""
        if request.META.get('HTTP_IF_NONE_MATCH') == etag:
            return Response(status=304)
        response = super().retrieve(request, *args, **kwargs)
        try:
            if etag:
                response['ETag'] = etag
            if hist:
                response['Last-Modified'] = http_date(int(hist.timestamp()))
        except Exception:
            pass
        return response

    @extend_schema(
        summary='List objects (Vuetify table optimized)',
        parameters=[
            OpenApiParameter('page', int, OpenApiParameter.QUERY),
            OpenApiParameter('limit', int, OpenApiParameter.QUERY),
            OpenApiParameter('sortBy', str, OpenApiParameter.QUERY),
            OpenApiParameter('sortDesc', bool, OpenApiParameter.QUERY),
            OpenApiParameter('search', str, OpenApiParameter.QUERY),
        ],
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
