from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
import json
import numpy as np
import os
import tempfile
import zipfile

from django.db import connection
from django.utils.http import http_date
from django.utils.timezone import make_aware
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Sum, Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, extend_schema_view, OpenApiExample
import logging
logger = logging.getLogger(__name__)

from obs_run.models import ObservationRun
from objects.models import Object
from .serializers import RunSerializer
from .filter import RunFilter
from ..plotting import (
    plot_visibility,
    plot_observation_conditions,
    plot_sky_fov,
    plot_sky_fov_with_constellations,
    time_distribution_model,
)
from django.http import HttpResponse
from astropy.io import fits
from astropy.visualization import ZScaleInterval, ImageNormalize, AsinhStretch
try:
    from PIL import Image
except Exception:
    Image = None
from objects.models import Object
from rest_framework.decorators import api_view
import environ
from ..auxil import get_size_dir
from obs_run.models import DataFile


class RunsPagination(PageNumberPagination):
    """
    Pagination aligned with Objects: accepts `limit` (and supports -1 for "All").
    """
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 1000

    def get_page_size(self, request):
        raw = request.query_params.get('limit')
        if raw is None:
            raw = request.query_params.get('page_size')
        try:
            page_size = int(raw) if raw is not None else self.page_size
            if page_size == -1:
                return 10000
            return min(page_size, self.max_page_size)
        except (TypeError, ValueError):
            return self.page_size


@extend_schema_view(
    list=extend_schema(tags=['Runs']),
    retrieve=extend_schema(tags=['Runs']),
    create=extend_schema(tags=['Runs']),
    update=extend_schema(tags=['Runs']),
    partial_update=extend_schema(tags=['Runs']),
    destroy=extend_schema(tags=['Runs']),
)
class RunViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all observation runs in the database
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = ObservationRun.objects.all()
    serializer_class = RunSerializer
    pagination_class = RunsPagination
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = RunFilter
    ordering_fields = ['name', 'mid_observation_jd', 'reduction_status']
    ordering = ['mid_observation_jd']

    def get_queryset(self):
        # Prefetch tags and annotate light-weight aggregates for list views
        qs = ObservationRun.objects.all().prefetch_related('tags').annotate(
            n_fits=Count('datafile', filter=Q(datafile__file_type__exact='FITS')),
            n_img=(
                Count('datafile', filter=Q(datafile__file_type__exact='JPG')) +
                Count('datafile', filter=Q(datafile__file_type__exact='CR2')) +
                Count('datafile', filter=Q(datafile__file_type__exact='TIFF'))
            ),
            n_ser=Count('datafile', filter=Q(datafile__file_type__exact='SER')),
            n_light=Count('datafile', filter=Q(datafile__exposure_type__exact='LI')),
            n_flat=Count('datafile', filter=Q(datafile__exposure_type__exact='FL')),
            n_dark=Count('datafile', filter=Q(datafile__exposure_type__exact='DA')),
            expo_time=Sum('datafile__exptime', filter=Q(datafile__exptime__gt=0)),
            n_datafiles=Count('datafile'),
        )
        # Anonymous users only see public runs
        try:
            if not getattr(self.request, 'user', None) or self.request.user.is_anonymous:
                qs = qs.filter(is_public=True)
        except Exception:
            pass
        return qs

    def _has(self, user, codename: str) -> bool:
        try:
            return bool(user and (user.is_superuser or user.has_perm(f'users.{codename}')))
        except Exception:
            return False

    def get_permissions(self):
        return [IsAuthenticatedOrReadOnly()]

    def update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_runs_edit'):
            return Response({'detail': 'Forbidden'}, status=403)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_runs_edit'):
            return Response({'detail': 'Forbidden'}, status=403)
        try:
            data = request.data if hasattr(request, 'data') else {}
            if 'is_public' in data and not self._has(request.user, 'acl_runs_publish'):
                return Response({'detail': 'Forbidden (publish)'}, status=403)
        except Exception:
            pass
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_runs_delete'):
            return Response({'detail': 'Forbidden'}, status=403)
        return super().destroy(request, *args, **kwargs)

    # (replaced by the combined get_queryset above)

    def get_serializer_class(self):
        return RunSerializer

    @extend_schema(
        summary='List observation runs',
        description='Paginated list of observation runs with filtering and ordering.',
        parameters=[
            OpenApiParameter(name='page', description='Page number', required=False, type=int),
            OpenApiParameter(name='limit', description='Items per page', required=False, type=int),
            OpenApiParameter(name='ordering', description='name|mid_observation_jd|reduction_status (prefix with - for desc)', required=False, type=str),
            OpenApiParameter(name='status', description='Filter by reduction status (NE|PR|FR|ER)', required=False, type=str),
        ],
    )
    def list(self, request, *args, **kwargs):
        """
        Validate ordering and gracefully fall back to a safe default to avoid errors.
        Adds ETag and Last-Modified for conditional GETs.
        """
        queryset = self.filter_queryset(self.get_queryset())
        ordering_param = (request.query_params.get('ordering') or '').strip()
        if ordering_param:
            desc = ordering_param.startswith('-')
            field = ordering_param.lstrip('-')
            allowed = set(self.ordering_fields or [])
            alias = {'date': 'mid_observation_jd'}
            if field in alias:
                mapped = alias[field]
                queryset = queryset.order_by(f"{'-' if desc else ''}{mapped}")
            elif field not in allowed:
                queryset = queryset.order_by('mid_observation_jd')
        try:
            from obs_run.models import ObservationRun, DataFile  # local import safe
            from django.db.models import Max
            latest_run_hist = ObservationRun.history.aggregate(m=Max('history_date'))['m']
            latest_df_hist = DataFile.history.aggregate(m=Max('history_date'))['m']
            count = queryset.count()
            # Include DataFile history in the signature so ETag changes when file counts change
            sig = f"runs:{count}:{str(latest_run_hist)}:{str(latest_df_hist)}:{hash(request.META.get('QUERY_STRING',''))}"
            etag = f"W/\"{abs(hash(sig))}\""
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
            if if_none_match and if_none_match == etag:
                return Response(status=304)
        except Exception:
            etag = None
            latest_hist = None
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            resp = self.get_paginated_response(serializer.data)
            try:
                if etag:
                    resp['ETag'] = etag
                if latest_hist:
                    resp['Last-Modified'] = http_date(int(latest_hist.timestamp()))
                if request.user.is_anonymous:
                    resp['Cache-Control'] = 'public, max-age=60'
            except Exception:
                pass
            return resp
        serializer = self.get_serializer(queryset, many=True)
        resp = Response(serializer.data)
        try:
            if etag:
                resp['ETag'] = etag
            # Prefer the latest of run/file histories if available
            try:
                from django.db.models import Max
                from obs_run.models import ObservationRun, DataFile
                latest_run_hist = ObservationRun.history.aggregate(m=Max('history_date'))['m']
                latest_df_hist = DataFile.history.aggregate(m=Max('history_date'))['m']
                latest_hist_any = max([d for d in [latest_run_hist, latest_df_hist] if d is not None], default=None)
            except Exception:
                latest_hist_any = None
            if latest_hist_any:
                resp['Last-Modified'] = http_date(int(latest_hist_any.timestamp()))
            if request.user.is_anonymous:
                resp['Cache-Control'] = 'public, max-age=60'
        except Exception:
            pass
        return resp

    @extend_schema(summary='Retrieve observation run', description='Get an observation run by ID.')
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            hist = instance.history.order_by('-history_date').values_list('history_date', flat=True).first()
            # Also include latest change of any related DataFile to avoid stale detail responses
            from django.db.models import Max
            from obs_run.models import DataFile
            df_hist = DataFile.history.filter(observation_run=instance).aggregate(m=Max('history_date'))['m']
            latest_any = max([d for d in [hist, df_hist] if d is not None], default=None)
        except Exception:
            latest_any = None
        sig = f"run:{instance.pk}:{str(latest_any)}"
        etag = f"W/\"{abs(hash(sig))}\""
        if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
        if if_none_match and if_none_match == etag:
            return Response(status=304)
        serializer = self.get_serializer(instance)
        resp = Response(serializer.data)
        try:
            if etag:
                resp['ETag'] = etag
            if latest_any:
                resp['Last-Modified'] = http_date(int(latest_any.timestamp()))
        except Exception:
            pass
        return resp


@extend_schema(
    summary='Visibility plot',
    description='Returns a Bokeh JSON item for visibility given run_id, coordinates and time.',
    tags=['Runs', 'Plots'],
    parameters=[
        OpenApiParameter('run_id', int, OpenApiParameter.QUERY),
        OpenApiParameter('ra', float, OpenApiParameter.QUERY),
        OpenApiParameter('dec', float, OpenApiParameter.QUERY),
        OpenApiParameter('start_hjd', float, OpenApiParameter.QUERY),
        OpenApiParameter('expo_time', float, OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
def get_visibility_plot(request):
    try:
        run_id = float(request.query_params.get('run_id'))
        ra = float(request.query_params.get('ra'))
        dec = float(request.query_params.get('dec'))
        start_hjd = request.query_params.get('start_hjd')
        expo_time = request.query_params.get('expo_time')
        start_hjd = float(start_hjd) if start_hjd is not None else None
        expo_time = float(expo_time) if expo_time is not None else 0.0
        if start_hjd is None:
            return Response({'error': 'start_hjd required'}, status=400)
        fig = plot_visibility(start_hjd, expo_time or 0.0, ra, dec)
        from bokeh.embed import json_item
        return Response(json_item(fig))
    except Exception as e:
        logger.exception("visibility plot failed: %s", e)
        return Response({'error': str(e)}, status=400)


@extend_schema(summary='Observing conditions plot', description='Returns a Bokeh JSON item (Tabs) for observing conditions of a run.', tags=['Runs', 'Plots'])
@api_view(['GET'])
def get_observing_conditions(request, run_pk):
    try:
        tabs = plot_observation_conditions(run_pk)
        from bokeh.embed import json_item
        return Response(json_item(tabs))
    except Exception as e:
        logger.exception("observing conditions failed for run %s: %s", run_pk, e)
        return Response({'error': str(e)}, status=400)


@extend_schema(
    summary='Sky FOV plot',
    tags=['Runs', 'Plots'],
    parameters=[
        OpenApiParameter('ra', float, OpenApiParameter.QUERY),
        OpenApiParameter('dec', float, OpenApiParameter.QUERY),
        OpenApiParameter('fov_x', float, OpenApiParameter.QUERY),
        OpenApiParameter('fov_y', float, OpenApiParameter.QUERY),
        OpenApiParameter('scale', float, OpenApiParameter.QUERY),
        OpenApiParameter('rotation', float, OpenApiParameter.QUERY),
        OpenApiParameter('constellations', bool, OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
def get_sky_fov(request):
    try:
        ra = float(request.query_params.get('ra'))
        dec = float(request.query_params.get('dec'))
        fov_x = float(request.query_params.get('fov_x'))
        fov_y = float(request.query_params.get('fov_y'))
        scale = float(request.query_params.get('scale', 8.0))
        rotation = float(request.query_params.get('rotation', 0.0))
        show_const = request.query_params.get('constellations', 'false').lower() == 'true'
        if show_const:
            fig = plot_sky_fov_with_constellations(ra, dec, fov_x, fov_y, scale=scale, rotation_deg=rotation, show_constellations=True)
        else:
            fig = plot_sky_fov(ra, dec, fov_x, fov_y, scale=scale, rotation_deg=rotation)
        from bokeh.embed import json_item
        return Response(json_item(fig))
    except Exception as e:
        logger.exception("sky FOV failed: %s", e)
        return Response({'error': str(e)}, status=400)


@extend_schema(
    summary='Time distribution plot',
    tags=['Runs', 'Plots'],
    parameters=[
        OpenApiParameter('model', str, OpenApiParameter.QUERY, description='run|object'),
        OpenApiParameter('label', str, OpenApiParameter.QUERY),
        OpenApiParameter('months', int, OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
def get_time_distribution(request):
    try:
        model = (request.query_params.get('model') or 'run').lower()
        label = request.query_params.get('label') or ('Runs' if model == 'run' else 'Objects')
        months_param = (request.query_params.get('months') or 'all').lower()
        months = None if months_param in ('all', '') else int(months_param)
        if model == 'run':
            fig = time_distribution_model(ObservationRun, label, months=months)
        else:
            fig = time_distribution_model(Object, label, months=months)
        from bokeh.embed import json_item
        return Response(json_item(fig))
    except Exception as e:
        logger.exception("time distribution failed: %s", e)
        return Response({'error': str(e)}, status=400)


# Scoped throttling for plots
get_time_distribution.throttle_classes = [ScopedRateThrottle]
get_time_distribution.throttle_scope = 'plots'
get_visibility_plot.throttle_classes = [ScopedRateThrottle]
get_visibility_plot.throttle_scope = 'plots'
get_sky_fov.throttle_classes = [ScopedRateThrottle]
get_sky_fov.throttle_scope = 'plots'
get_observing_conditions.throttle_classes = [ScopedRateThrottle]
get_observing_conditions.throttle_scope = 'plots'


@api_view(['GET'])
def getDashboardStats(request):
    """
    Get statistics for the dashboard including file counts, types and object statistics
    """
    try:
        from django.core.cache import cache
        cached = cache.get('dashboard_stats_v1')
        if cached:
            return Response(cached)
    except Exception:
        cached = None
    dtime_naive = datetime.now() - timedelta(days=7)
    aware_datetime = make_aware(dtime_naive)
    files = DataFile.objects.all()
    files_7d = DataFile.history.filter(history_date__gte=aware_datetime)
    objects = Object.objects.all()
    objects_7d = Object.history.filter(history_date__gte=aware_datetime)
    runs = ObservationRun.objects.all()
    runs_7d = ObservationRun.history.filter(history_date__gte=aware_datetime)
    stats = {
        'files': {
            'total': files.count(),
            'total_last_week': files_7d.count(),
            'bias': files.filter(exposure_type='BI').count(),
            'darks': files.filter(exposure_type='DA').count(),
            'flats': files.filter(exposure_type='FL').count(),
            'lights': files.filter(exposure_type='LI').count(),
            'waves': files.filter(exposure_type='WA').count(),
            'fits': files.filter(file_type__exact='FITS').count(),
            'jpeg': files.filter(file_type__exact='JPG').count(),
            'cr2': files.filter(file_type__exact='CR2').count(),
            'tiff': files.filter(file_type__exact='TIFF').count(),
            'ser': files.filter(file_type__exact='SER').count()
        },
        'objects': {
            'total': objects.count(),
            'total_last_week': objects_7d.count(),
            'galaxies': objects.filter(object_type='GA').count(),
            'star_clusters': objects.filter(object_type='SC').count(),
            'nebulae': objects.filter(object_type='NE').count(),
            'stars': objects.filter(object_type='ST').count(),
            'solar_system': objects.filter(object_type='SO').count(),
            'other': objects.filter(object_type='OT').count(),
            'unknown': objects.filter(object_type='UK').count()
        },
        'runs': {
            'total': runs.count(),
            'total_last_week': runs_7d.count(),
            'partly_reduced': runs.filter(reduction_status='PR').count(),
            'fully_reduced': runs.filter(reduction_status='FR').count(),
            'reduction_error': runs.filter(reduction_status='ER').count(),
            'not_reduced': runs.filter(reduction_status='NE').count()
        }
    }
    env = environ.Env()
    environ.Env.read_env()
    data_path = env("DATA_DIRECTORY", default='/archive/ftp/')
    stats['files']['storage_size'] = get_size_dir(data_path) * pow(1000, -4)
    try:
        if 'cache' in globals() or 'cache' in locals():
            cache.set('dashboard_stats_v1', stats, timeout=300)
    except Exception:
        pass
    return Response(stats)

# Throttle dashboard stats modestly
getDashboardStats.throttle_classes = [ScopedRateThrottle]
getDashboardStats.throttle_scope = 'stats'


