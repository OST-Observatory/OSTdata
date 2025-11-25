from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAdminUser, IsAuthenticated

from django_filters.rest_framework import DjangoFilterBackend

from obs_run.models import ObservationRun, DataFile
from ostdata.custom_permissions import IsAllowedOnRun, get_allowed_model_to_view_for_user

from .serializers import RunSerializer, RunListSerializer, DataFileSerializer
from ..plotting import (
    plot_visibility,
    plot_observation_conditions,
    plot_sky_fov,
    plot_sky_fov_with_constellations,
    time_distribution_model,
)
from obs_run.models import ObservationRun
from objects.models import Object
from .filter import RunFilter, DataFileFilter

from django.utils.timezone import make_aware
from datetime import datetime, timedelta
import environ
from ..auxil import get_size_dir
from objects.models import Object
from django.http import HttpResponse
from io import BytesIO
from pathlib import Path
import os
import tempfile
import zipfile
import numpy as np
from astropy.io import fits
from astropy.visualization import ZScaleInterval, ImageNormalize, AsinhStretch
try:
    from PIL import Image
except Exception:
    Image = None

from django.utils import timezone
from django.db import transaction
from obs_run.models import DownloadJob
from obs_run.tasks import build_zip_task
from obs_run.tasks import cleanup_expired_downloads, reconcile_filesystem
from obs_run.tasks import cleanup_orphans_and_hashcheck
from django.db import connection
import platform
import sys
import time as _time
import json
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.throttling import ScopedRateThrottle
from django.utils.http import http_date
from drf_spectacular.utils import extend_schema, OpenApiParameter
try:
    import redis as _redis
except Exception:
    _redis = None
try:
    import django
    _django_version = getattr(django, 'get_version', lambda: '')()
except Exception:
    _django_version = ''
try:
    import ldap as _ldap
except Exception:
    _ldap = None
try:
    # Import Celery app to ping workers
    from ostdata.celery import app as celery_app
except Exception:
    celery_app = None


# ===============================================================
#   OBSERVATION RUNS
# ===============================================================

class RunsPagination(PageNumberPagination):
    """
    Pagination aligned with Objects: accepts `limit` (and supports -1 for "All").
    """
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 1000

    def get_page_size(self, request):
        # Accept both limit and page_size for compatibility
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
        # Prefetch tags to avoid N+1 in list
        return ObservationRun.objects.all().prefetch_related('tags')

    def _has(self, user, codename: str) -> bool:
        try:
            return bool(user and (user.is_superuser or user.has_perm(f'users.{codename}')))
        except Exception:
            return False

    def get_permissions(self):
        # Use auth-or-readonly; enforce ACL in handlers for unsafe ops
        return [IsAuthenticatedOrReadOnly()]

    def update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_runs_edit'):
            return Response({'detail': 'Forbidden'}, status=403)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        # Editing any fields requires runs_edit; toggling publication additionally checked below
        if not self._has(request.user, 'acl_runs_edit'):
            return Response({'detail': 'Forbidden'}, status=403)
        # If is_public is being changed, require publish permission
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

    def get_queryset(self):
        queryset = ObservationRun.objects.all()
        if self.request.user.is_anonymous:
            return queryset.filter(is_public=True)
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return RunListSerializer
        if self.action == 'retrieve':
            return RunSerializer
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
        # Handle ordering aliases and invalid fields gracefully
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
                # Fallback to default ordering if invalid field is supplied
                queryset = queryset.order_by('mid_observation_jd')
        # Conditional GET: ETag/Last-Modified based on history and count + query string
        try:
            from obs_run.models import ObservationRun  # local import safe
            from django.db.models import Max
            # For Last-Modified use latest history_date if available; fallback to None
            latest_hist = ObservationRun.history.aggregate(m=Max('history_date'))['m']
            count = queryset.count()
            sig = f"runs:{count}:{str(latest_hist)}:{hash(request.META.get('QUERY_STRING',''))}"
            etag = f"W/\"{abs(hash(sig))}\""
            if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
            if if_none_match and if_none_match == etag:
                return Response(status=304)
        except Exception:
            etag = None
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            resp = self.get_paginated_response(serializer.data)
            try:
                if etag:
                    resp['ETag'] = etag
                if latest_hist:
                    resp['Last-Modified'] = http_date(int(latest_hist.timestamp()))
            except Exception:
                pass
            return resp
        serializer = self.get_serializer(queryset, many=True)
        resp = Response(serializer.data)
        try:
            if etag:
                resp['ETag'] = etag
            if latest_hist:
                resp['Last-Modified'] = http_date(int(latest_hist.timestamp()))
        except Exception:
            pass
        return resp

    @extend_schema(summary='Retrieve observation run', description='Get an observation run by ID.')
    def retrieve(self, request, *args, **kwargs):
        """Detail view with conditional GET headers."""
        instance = self.get_object()
        # Compute Last-Modified from history
        try:
            hist = instance.history.order_by('-history_date').values_list('history_date', flat=True).first()
        except Exception:
            hist = None
        sig = f"run:{instance.pk}:{str(hist)}"
        etag = f"W/\"{abs(hash(sig))}\""
        if_none_match = request.META.get('HTTP_IF_NONE_MATCH')
        if if_none_match and if_none_match == etag:
            return Response(status=304)
        serializer = self.get_serializer(instance)
        resp = Response(serializer.data)
        try:
            if etag:
                resp['ETag'] = etag
            if hist:
                resp['Last-Modified'] = http_date(int(hist.timestamp()))
        except Exception:
            pass
        return resp



class DataFilesPagination(PageNumberPagination):
    """
    Pagination for DataFile endpoints: accepts `limit` (and supports -1 for "All").
    Mirrors RunsPagination for consistency with other list views.
    """
    page_size = 10
    page_size_query_param = 'limit'
    max_page_size = 10000

    def get_page_size(self, request):
        raw = request.query_params.get('limit')
        if raw is None:
            raw = request.query_params.get('page_size')
        try:
            page_size = int(raw) if raw is not None else self.page_size
            if page_size == -1:
                return self.max_page_size
            return min(page_size, self.max_page_size)
        except (TypeError, ValueError):
            return self.page_size

@api_view(['GET'])
def getRunDataFile(request, run_pk):
    """
    DEPRECATED: This endpoint has been removed in favor of the generic /api/runs/datafiles/ with filters.
    """
    return Response({"detail": "Not found"}, status=404)


@api_view(['GET'])
def get_datafile_thumbnail(request, pk):
    """
    Return a PNG thumbnail for the given DataFile.
    FITS uses ZScale + asinh stretch; JPG/TIFF are thumbnailed directly.
    Optional query params: w (int, default 512)
    """
    try:
        df = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    max_dim = 512
    try:
        w = int(request.query_params.get('w', max_dim))
        if w > 2048:
            w = 2048
        if w <= 0:
            w = max_dim
    except Exception:
        w = max_dim

    path = df.datafile
    file_type = (df.file_type or '').upper()
    file_path = Path(path)
    if not file_path.exists():
        return Response({"detail": "File not found"}, status=404)

    # Determine FITS by type or extension (fallback)
    is_fits = (file_type == 'FITS') or (file_path.suffix.lower() in ['.fits', '.fit', '.fts'])

    try:
        # FITS handling with zscale
        if is_fits:
            # Some FITS with BZERO/BSCALE/BLANK cannot be memory-mapped; disable memmap
            with fits.open(str(file_path), memmap=False) as hdul:
                data = None
                # Prefer first image-like HDU with 2D data
                for hdu in hdul:
                    if hasattr(hdu, 'data') and hdu.data is not None:
                        arr = np.asarray(hdu.data)
                        if arr.ndim >= 2:
                            data = arr
                            break
                if data is None:
                    return Response({"detail": "No image data"}, status=400)
                if data.ndim > 2:
                    data = data[0]
                # Replace non-finite
                data = np.asarray(data, dtype=float)
                finite = np.isfinite(data)
                if not finite.any():
                    return Response({"detail": "Invalid image data"}, status=400)
                zscale = ZScaleInterval()
                vmin, vmax = zscale.get_limits(data[finite])
                norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch())
                scaled = norm(data)
                scaled = np.clip(scaled, 0.0, 1.0)
                img8 = (scaled * 255.0).astype(np.uint8)
                # Create image
                if Image is None:
                    # Minimal fallback using numpy tobytes and raw PNG via PIL unavailable
                    # Without PIL, cannot encode PNG easily; return error
                    return Response({"detail": "PIL not available"}, status=500)
                img = Image.fromarray(img8, mode='L')
                img.thumbnail((w, w))
                buf = BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                return HttpResponse(buf.getvalue(), content_type='image/png')
        else:
            # Non-FITS: try PIL thumbnail
            if Image is None:
                return Response({"detail": "Preview not supported"}, status=400)
            img = Image.open(str(file_path))
            img.thumbnail((w, w))
            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            return HttpResponse(buf.getvalue(), content_type='image/png')
    except Exception as e:
        return Response({"detail": str(e)}, status=400)


@api_view(['GET'])
def get_datafile_header(request, pk):
    """
    Return sanitized FITS header for a DataFile as JSON. If the user is anonymous,
    only headers for files in public runs are accessible.
    """
    try:
        df = DataFile.objects.select_related('observation_run').get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    run = df.observation_run
    if request.user.is_anonymous and run and not run.is_public:
        return Response({"detail": "Not found"}, status=404)

    file_path = Path(df.datafile)
    if not file_path.exists() or not file_path.is_file():
        return Response({"detail": "File not found"}, status=404)

    # Determine FITS by type or extension
    file_type = (df.file_type or '').upper()
    is_fits = (file_type == 'FITS') or (file_path.suffix.lower() in ['.fits', '.fit', '.fts'])
    if not is_fits:
        return Response({"header": {}}, status=200)

    try:
        header = df.get_fits_header()
        return Response({"header": header}, status=200)
    except Exception as e:
        return Response({"detail": str(e)}, status=400)


@api_view(['GET'])
def download_datafile(request, pk):
    """
    Send the raw data file as an attachment if the user has access to the run.
    """
    try:
        df = DataFile.objects.select_related('observation_run').get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    run = df.observation_run
    if request.user.is_anonymous and run and not run.is_public:
        return Response({"detail": "Not found"}, status=404)

    file_path = Path(df.datafile)
    if not file_path.exists() or not file_path.is_file():
        return Response({"detail": "File not found"}, status=404)

    try:
        from django.http import FileResponse
        resp = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=Path(df.datafile).name)
        return resp
    except Exception as e:
        return Response({"detail": str(e)}, status=400)


@api_view(['GET'])
def download_run_datafiles(request, run_pk):
    """
    Create a ZIP archive of data files for a run. Optional query param `ids` (comma-separated)
    to restrict which files to include.
    """
    try:
        run = ObservationRun.objects.get(pk=run_pk)
    except ObservationRun.DoesNotExist:
        return Response({"detail": "Run not found"}, status=404)

    if request.user.is_anonymous and not run.is_public:
        return Response({"detail": "Not found"}, status=404)

    qs = DataFile.objects.filter(observation_run_id=run_pk)
    ids_param = request.query_params.get('ids')
    if ids_param:
        try:
            id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
            if id_list:
                qs = qs.filter(pk__in=id_list)
        except Exception:
            pass

    # Apply optional filter parameters (same as API list):
    q_params = request.query_params
    if q_params.get('file_type'):
        qs = qs.filter(file_type__icontains=q_params.get('file_type'))
    if q_params.get('main_target'):
        # Reuse tokenized logic simply: require substring match; for stricter use same token split
        from django.db.models import Q
        val = q_params.get('main_target')
        qs = qs.filter(Q(main_target__icontains=val) | Q(header_target_name__icontains=val))
    if q_params.getlist('exposure_type'):
        qs = qs.filter(exposure_type__in=q_params.getlist('exposure_type'))
    if q_params.get('spectroscopy') is not None:
        val = q_params.get('spectroscopy')
        if val.lower() in ('true', '1', 'yes'):
            qs = qs.filter(spectroscopy=True)
        if val.lower() in ('false', '0', 'no'):
            qs = qs.filter(spectroscopy=False)
    if q_params.get('exptime_min') is not None:
        qs = qs.filter(exptime__gte=q_params.get('exptime_min'))
    if q_params.get('exptime_max') is not None:
        qs = qs.filter(exptime__lte=q_params.get('exptime_max'))
    if q_params.get('file_name'):
        qs = qs.filter(datafile__icontains=q_params.get('file_name'))
    if q_params.get('instrument'):
        qs = qs.filter(instrument__icontains=q_params.get('instrument'))
    # Pixel count filtering
    from django.db.models import F, FloatField, ExpressionWrapper
    if q_params.get('pixel_count_min') is not None or q_params.get('pixel_count_max') is not None:
        qs = qs.annotate(pixel_count=ExpressionWrapper(F('naxis1') * F('naxis2'), output_field=FloatField()))
        if q_params.get('pixel_count_min') is not None:
            qs = qs.filter(pixel_count__gte=q_params.get('pixel_count_min'))
        if q_params.get('pixel_count_max') is not None:
            qs = qs.filter(pixel_count__lte=q_params.get('pixel_count_max'))

    files = list(qs)
    if not files:
        return Response({"detail": "No files to download"}, status=400)

    # Create temporary ZIP
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp_path = tmp.name
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for df in files:
                p = Path(df.datafile)
                if p.exists() and p.is_file():
                    arcname = f"{df.pk}_{p.name}"
                    try:
                        zf.write(p, arcname=arcname)
                    except Exception:
                        continue
        from django.http import FileResponse
        filename = f"run_{run_pk}_datafiles.zip"
        resp = FileResponse(open(tmp_path, 'rb'), as_attachment=True, filename=filename)
        return resp
    except Exception as e:
        return Response({"detail": str(e)}, status=400)


@api_view(['GET'])
def download_datafiles_bulk(request):
    """
    Create a ZIP of arbitrary datafiles selected by ids or by filters (across runs).
    Query params:
      - ids: comma-separated list of DataFile PKs (optional)
      - filters: same subset as run download (file_type, main_target, exposure_type, spectroscopy,
                 exptime_min, exptime_max, file_name, instrument, pixel_count_min/max)
    Access: anonymous users only get files belonging to public runs.
    """
    qs = DataFile.objects.all().select_related('observation_run')

    # Visibility for anonymous users
    if request.user.is_anonymous:
        qs = qs.filter(observation_run__is_public=True)

    # Apply ids constraint first if provided
    ids_param = request.query_params.get('ids')
    if ids_param:
        try:
            id_list = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
            if id_list:
                qs = qs.filter(pk__in=id_list)
        except Exception:
            pass

    # Apply optional filters
    q_params = request.query_params
    if q_params.get('file_type'):
        qs = qs.filter(file_type__icontains=q_params.get('file_type'))
    if q_params.get('main_target'):
        from django.db.models import Q
        val = q_params.get('main_target')
        qs = qs.filter(Q(main_target__icontains=val) | Q(header_target_name__icontains=val))
    if q_params.getlist('exposure_type'):
        qs = qs.filter(exposure_type__in=q_params.getlist('exposure_type'))
    if q_params.get('spectroscopy') is not None:
        val = q_params.get('spectroscopy')
        if isinstance(val, str):
            v = val.lower()
            if v in ('true', '1', 'yes'):
                qs = qs.filter(spectroscopy=True)
            elif v in ('false', '0', 'no'):
                qs = qs.filter(spectroscopy=False)
    if q_params.get('exptime_min') is not None:
        qs = qs.filter(exptime__gte=q_params.get('exptime_min'))
    if q_params.get('exptime_max') is not None:
        qs = qs.filter(exptime__lte=q_params.get('exptime_max'))
    if q_params.get('file_name'):
        qs = qs.filter(datafile__icontains=q_params.get('file_name'))
    if q_params.get('instrument'):
        qs = qs.filter(instrument__icontains=q_params.get('instrument'))
    from django.db.models import F, FloatField, ExpressionWrapper
    if q_params.get('pixel_count_min') is not None or q_params.get('pixel_count_max') is not None:
        qs = qs.annotate(pixel_count=ExpressionWrapper(F('naxis1') * F('naxis2'), output_field=FloatField()))
        if q_params.get('pixel_count_min') is not None:
            qs = qs.filter(pixel_count__gte=q_params.get('pixel_count_min'))
        if q_params.get('pixel_count_max') is not None:
            qs = qs.filter(pixel_count__lte=q_params.get('pixel_count_max'))

    files = list(qs)
    if not files:
        return Response({"detail": "No files to download"}, status=400)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp_path = tmp.name
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for df in files:
                p = Path(df.datafile)
                if p.exists() and p.is_file():
                    arcname = f"{df.pk}_{p.name}"
                    try:
                        zf.write(p, arcname=arcname)
                    except Exception:
                        continue
        from django.http import FileResponse
        filename = f"datafiles_filtered.zip"
        resp = FileResponse(open(tmp_path, 'rb'), as_attachment=True, filename=filename)
        return resp
    except Exception as e:
        return Response({"detail": str(e)}, status=400)


@extend_schema(
    summary='Visibility plot',
    description='Returns a Bokeh JSON item for visibility given run_id, coordinates and time.',
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
    """
    Return a Bokeh JSON item for a visibility plot for a given object within a run.
    Query params:
      - run_id (int)
      - ra (float degrees)
      - dec (float degrees)
      - start_hjd (float, optional); if not provided and observed_start is available, prefer that
      - expo_time (float seconds, optional)
    """
    try:
        run_id = float(request.query_params.get('run_id'))
        ra = float(request.query_params.get('ra'))
        dec = float(request.query_params.get('dec'))
        start_hjd = request.query_params.get('start_hjd')
        expo_time = request.query_params.get('expo_time')
        start_hjd = float(start_hjd) if start_hjd is not None else None
        expo_time = float(expo_time) if expo_time is not None else 0.0

        # Fallback: if start_hjd missing, try to derive from run mid and use expo_time
        if start_hjd is None:
            # Without precise per-object HJD, approximate from run name (mid night) is not reliable; require param
            return Response({'error': 'start_hjd required'}, status=400)

        fig = plot_visibility(start_hjd, expo_time or 0.0, ra, dec)
        from bokeh.embed import json_item
        return Response(json_item(fig))
    except Exception as e:
        return Response({'error': str(e)}, status=400)


@extend_schema(summary='Observing conditions plot', description='Returns a Bokeh JSON item (Tabs) for observing conditions of a run.')
@api_view(['GET'])
def get_observing_conditions(request, run_pk):
    """
    Return a Bokeh JSON item (Tabs) for observing conditions of a run.
    """
    try:
        tabs = plot_observation_conditions(run_pk)
        from bokeh.embed import json_item
        return Response(json_item(tabs))
    except Exception as e:
        return Response({'error': str(e)}, status=400)

# (moved throttling assignments below function definitions to avoid NameError)


@extend_schema(
    summary='Sky FOV plot',
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
    """
    Returns Bokeh json_item for a sky region with camera FOV overlay.
    Query params: ra, dec, fov_x, fov_y, scale (optional, default 8), rotation (optional)
    """
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
        return Response({'error': str(e)}, status=400)


@extend_schema(
    summary='Time distribution plot',
    parameters=[
        OpenApiParameter('model', str, OpenApiParameter.QUERY, description='run|object'),
        OpenApiParameter('label', str, OpenApiParameter.QUERY),
        OpenApiParameter('months', int, OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
def get_time_distribution(request):
    """
    Returns Bokeh json_item for time distribution of runs or objects.
    Query params: model=run|object, label
    """
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
        return Response({'error': str(e)}, status=400)

# Scoped throttling for time distribution and dashboard stats
get_time_distribution.throttle_classes = [ScopedRateThrottle]
get_time_distribution.throttle_scope = 'plots'
get_visibility_plot.throttle_classes = [ScopedRateThrottle]
get_visibility_plot.throttle_scope = 'plots'
get_sky_fov.throttle_classes = [ScopedRateThrottle]
get_sky_fov.throttle_scope = 'plots'
get_observing_conditions.throttle_classes = [ScopedRateThrottle]
get_observing_conditions.throttle_scope = 'plots'

@api_view(['GET'])
def get_bokeh_version(request):
    """
    DEPRECATED: Bokeh version is surfaced via admin health; frontend loads version from env.
    """
    return Response({ 'version': '' }, status=410)

# ===============================================================
#   DATA FILE
# ===============================================================

class DataFileViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all stars/objects in the database
    """
    queryset = DataFile.objects.select_related('observation_run').all()
    serializer_class = DataFileSerializer
    pagination_class = DataFilesPagination

    filter_backends = (DjangoFilterBackend,)
    filterset_class = DataFileFilter

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Server-side binning filter (derived from FITS header), applied before pagination
        binning = request.query_params.get('binning')
        if binning:
            try:
                target = str(binning).strip().lower()
                ids = []
                # Evaluate only ids to avoid loading large objects; iterate reasonably
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

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

@api_view(['GET'])
def getDashboardStats(request):
    """
    Get statistics for the dashboard including file counts, types and object statistics
    """
    # Short-lived cache to avoid repeated heavy computations
    try:
        from django.core.cache import cache
        cached = cache.get('dashboard_stats_v1')
        if cached:
            return Response(cached)
    except Exception:
        cached = None
    # Set time frame of 7 days
    dtime_naive = datetime.now() - timedelta(days=7)
    aware_datetime = make_aware(dtime_naive)

    # Get all files and files added within the last 7 days
    files = DataFile.objects.all()
    files_7d = DataFile.history.filter(history_date__gte=aware_datetime)

    # Get all objects and objects added within the last 7 days
    objects = Object.objects.all()
    objects_7d = Object.history.filter(history_date__gte=aware_datetime)

    # Get all observation runs and runs added within the last 7 days
    runs = ObservationRun.objects.all()
    runs_7d = ObservationRun.history.filter(history_date__gte=aware_datetime)

    # Calculate file statistics
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

    # Get storage usage
    env = environ.Env()
    environ.Env.read_env()
    data_path = env("DATA_DIRECTORY", default='/archive/ftp/')
    stats['files']['storage_size'] = get_size_dir(data_path) * pow(1000, -4)  # Convert to TB

    try:
        if 'cache' in globals() or 'cache' in locals():
            cache.set('dashboard_stats_v1', stats, timeout=300)  # 5 minutes
    except Exception:
        pass
    return Response(stats)

# Throttle dashboard stats modestly
getDashboardStats.throttle_classes = [ScopedRateThrottle]
getDashboardStats.throttle_scope = 'stats'

@api_view(['POST'])
def create_download_job_bulk(request):
    """Create a DownloadJob for arbitrary datafiles (IDs and/or filters across runs)."""
    payload = request.data if hasattr(request, 'data') else {}
    selected_ids = payload.get('ids') or []
    filters = payload.get('filters') or {}

    job = DownloadJob.objects.create(
        user=request.user if request.user.is_authenticated else None,
        run=None,
        selected_ids=selected_ids,
        filters=filters,
        status='queued',
    )
    build_zip_task.delay(job.pk)
    return Response({'job_id': job.pk}, status=201)

@api_view(['POST'])
def create_download_job(request, run_pk):
    """Create a DownloadJob and enqueue the Celery task."""
    try:
        run = ObservationRun.objects.get(pk=run_pk)
    except ObservationRun.DoesNotExist:
        return Response({'detail': 'Run not found'}, status=404)

    if request.user.is_anonymous and not run.is_public:
        return Response({'detail': 'Not found'}, status=404)

    payload = request.data if hasattr(request, 'data') else {}
    selected_ids = payload.get('ids') or []
    filters = payload.get('filters') or {}

    with transaction.atomic():
        job = DownloadJob.objects.create(
            user=request.user if request.user.is_authenticated else None,
            run=run,
            selected_ids=selected_ids,
            filters=filters,
            status='queued',
        )
    build_zip_task.delay(job.pk)
    return Response({'job_id': job.pk}, status=201)


@api_view(['GET'])
def download_job_status(request, job_id):
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        return Response({'detail': 'Not found'}, status=404)
    if job.user_id and (not request.user.is_authenticated or request.user.pk != job.user_id):
        return Response({'detail': 'Not found'}, status=404)
    if job.user_id is None and request.user.is_anonymous and job.run and not job.run.is_public:
        return Response({'detail': 'Not found'}, status=404)
    return Response({
        'status': job.status,
        'progress': job.progress,
        'bytes_total': job.bytes_total,
        'bytes_done': job.bytes_done,
        'url': (f"/api/runs/jobs/{job.pk}/download" if job.status == 'done' and job.file_path else None),
        'error': job.error or None,
    })


@api_view(['GET'])
def list_download_jobs(request):
    """List download jobs. Admins see all; authenticated users see their own; anonymous see none."""
    qs = DownloadJob.objects.all().order_by('-created_at')
    if request.user.is_authenticated and request.user.is_staff:
        # Require ACL to view all jobs; otherwise restrict to own
        if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_view_all')):
            qs = qs.filter(user_id=request.user.pk)
    elif request.user.is_authenticated:
        qs = qs.filter(user_id=request.user.pk)
    else:
        qs = qs.none()

    # Optional filters: status, run, user
    status_param = request.query_params.get('status')
    if status_param:
        qs = qs.filter(status=status_param)
    run_param = request.query_params.get('run')
    if run_param:
        try:
            qs = qs.filter(run_id=int(run_param))
        except Exception:
            pass
    user_param = request.query_params.get('user')
    if user_param and request.user.is_authenticated and request.user.is_staff:
        try:
            qs = qs.filter(user_id=int(user_param))
        except Exception:
            pass

    # Simple serialization
    items = []
    for j in qs[:200]:
        items.append({
            'id': j.pk,
            'status': j.status,
            'progress': j.progress,
            'bytes_total': j.bytes_total,
            'bytes_done': j.bytes_done,
            'run': j.run_id,
            'user': j.user_id,
            'user_name': getattr(j.user, 'username', None),
            'created_at': j.created_at,
            'started_at': j.started_at,
            'finished_at': j.finished_at,
            'expires_at': j.expires_at,
            'error': j.error or '',
        })
    return Response({'items': items, 'total': qs.count()})


@api_view(['POST'])
def cancel_download_job(request, job_id):
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        return Response({'detail': 'Not found'}, status=404)
    # Owners can cancel their own jobs; admins can cancel any
    is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    if job.user_id and (not request.user.is_authenticated or (request.user.pk != job.user_id and not is_admin)):
        return Response({'detail': 'Not found'}, status=404)
    # If admin cancels someone else's job, require ACL
    if is_admin and job.user_id and request.user.pk != job.user_id:
        if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_cancel_any')):
            return Response({'detail': 'Forbidden'}, status=403)
    if job.status in ('done', 'failed', 'cancelled', 'expired'):
        return Response({'status': job.status, 'error': job.error or ''})
    job.status = 'cancelled'
    job.finished_at = timezone.now()
    # Provide a human-readable reason for consumers polling status and set expiry
    try:
        actor = 'administrator' if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False) else 'user'
        msg = f'Cancelled by {actor}'
        # Set expiry similar to 'done' so cleanup can run uniformly
        try:
            from datetime import timedelta
            from django.conf import settings
            ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
        except Exception:
            ttl_hours = 72
        job.expires_at = job.finished_at + timedelta(hours=ttl_hours)
        # Only overwrite if no prior error set
        if not job.error:
            job.error = msg
        else:
            # Preserve prior error but append cancel note for clarity
            job.error = f'{job.error} (cancelled by {actor})'
        job.save(update_fields=['status', 'finished_at', 'expires_at', 'error'])
    except Exception:
        job.save(update_fields=['status', 'finished_at'])
    # Signal cancel to workers via Redis key (optional fast path)
    try:
        broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('CELERY_BROKER_URL', '')
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            client.setex(f'job_cancel:{job.pk}', 24 * 3600, '1')
    except Exception:
        pass
    return Response({'status': job.status, 'error': job.error or ''})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def batch_cancel_download_jobs(request):
    """Admin: cancel multiple jobs by ids."""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_cancel_any')):
        return Response({'detail': 'Forbidden'}, status=403)
    ids = request.data.get('ids') or []
    try:
        ids = [int(x) for x in ids if str(x).strip().isdigit()]
    except Exception:
        ids = []
    if not ids:
        return Response({'cancelled': 0, 'skipped': 0}, status=200)
    now = timezone.now()
    cancelled = 0
    skipped = 0
    jobs = list(DownloadJob.objects.filter(pk__in=ids))
    for job in jobs:
        if job.status in ('done', 'failed', 'cancelled', 'expired'):
            skipped += 1
            continue
        job.status = 'cancelled'
        job.finished_at = now
        try:
            from datetime import timedelta
            from django.conf import settings
            ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
        except Exception:
            ttl_hours = 72
        job.expires_at = now + timedelta(hours=ttl_hours)
        try:
            note = 'Cancelled by administrator (batch)'
            job.error = note if not job.error else f'{job.error} (cancelled by administrator)'
            job.save(update_fields=['status', 'finished_at', 'expires_at', 'error'])
        except Exception:
            job.save(update_fields=['status', 'finished_at', 'expires_at'])
        cancelled += 1
    # Signal cancels via Redis flags
    try:
        broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('CELERY_BROKER_URL', '')
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            with client.pipeline() as pipe:
                for j in jobs:
                    try:
                        pipe.setex(f'job_cancel:{j.pk}', 24 * 3600, '1')
                    except Exception:
                        continue
                pipe.execute()
    except Exception:
        pass
    return Response({'cancelled': cancelled, 'skipped': skipped}, status=200)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def batch_extend_jobs_expiry(request):
    """Admin: extend expiry for multiple jobs by N hours (default 48)."""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_ttl_modify')):
        return Response({'detail': 'Forbidden'}, status=403)
    ids = request.data.get('ids') or []
    hours = request.data.get('hours')
    try:
        ids = [int(x) for x in ids if str(x).strip().isdigit()]
    except Exception:
        ids = []
    try:
        hours = int(hours) if hours is not None else 48
    except Exception:
        hours = 48
    if hours <= 0 or not ids:
        return Response({'updated': 0}, status=200)
    from datetime import timedelta
    now = timezone.now()
    updated = 0
    for job in DownloadJob.objects.filter(pk__in=ids):
        base = job.expires_at or now
        job.expires_at = base + timedelta(hours=hours)
        try:
            job.save(update_fields=['expires_at'])
            updated += 1
        except Exception:
            pass
    return Response({'updated': updated}, status=200)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def batch_expire_jobs_now(request):
    """Admin: immediately expire jobs (delete file if present, set status to expired)."""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_ttl_modify')):
        return Response({'detail': 'Forbidden'}, status=403)
    ids = request.data.get('ids') or []
    try:
        ids = [int(x) for x in ids if str(x).strip().isdigit()]
    except Exception:
        ids = []
    if not ids:
        return Response({'expired': 0}, status=200)
    now = timezone.now()
    expired = 0
    for job in DownloadJob.objects.filter(pk__in=ids):
        try:
            # Remove file if present
            if job.file_path:
                p = Path(job.file_path)
                try:
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            job.file_path = ''
            job.expires_at = now
            job.finished_at = job.finished_at or now
            job.status = 'expired'
            job.save(update_fields=['file_path', 'expires_at', 'finished_at', 'status'])
            expired += 1
        except Exception:
            pass
    return Response({'expired': expired}, status=200)


@api_view(['GET'])
def download_job_download(request, job_id):
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        return Response({'detail': 'Not found'}, status=404)
    if job.user_id and (not request.user.is_authenticated or request.user.pk != job.user_id):
        return Response({'detail': 'Not found'}, status=404)
    if job.status != 'done' or not job.file_path:
        return Response({'detail': 'Not ready'}, status=400)
    path = Path(job.file_path)
    if not path.exists():
        return Response({'detail': 'File missing'}, status=404)
    from django.http import FileResponse
    filename = path.name
    return FileResponse(open(path, 'rb'), as_attachment=True, filename=filename)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_trigger_cleanup_downloads(request):
    """Trigger cleanup of expired download jobs asynchronously."""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_cleanup')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        res = cleanup_expired_downloads.delay()
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None)}, status=202)
    except Exception as e:
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_trigger_reconcile(request):
    """Trigger filesystem reconcile asynchronously. Body: { dry_run: bool }"""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        dry_run = bool(request.data.get('dry_run', True)) if hasattr(request, 'data') else True
    except Exception:
        dry_run = True
    try:
        res = reconcile_filesystem.delay(dry_run=dry_run)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_trigger_orphans_hashcheck(request):
    """Trigger orphan cleanup and hash drift check. Body: { dry_run: bool, fix_missing_hashes: bool, limit: int|null }"""
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_orphans')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    try:
        dry_run = bool(payload.get('dry_run', True))
    except Exception:
        dry_run = True
    try:
        fix_missing_hashes = bool(payload.get('fix_missing_hashes', True))
    except Exception:
        fix_missing_hashes = True
    try:
        limit = payload.get('limit', None)
        limit = int(limit) if (limit is not None and str(limit).strip() != '') else None
    except Exception:
        limit = None
    try:
        res = cleanup_orphans_and_hashcheck.delay(dry_run=dry_run, fix_missing_hashes=fix_missing_hashes, limit=limit)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        return Response({'enqueued': False, 'error': str(e)}, status=400)

@extend_schema(summary='Admin system health (admin only)')
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_health(request):
    """Return system health information for admins."""
    # Enforce ACL: system health view
    if not (request.user and (request.user.is_superuser or request.user.has_perm('users.acl_system_health_view'))):
        return Response({'detail': 'Forbidden'}, status=403)
    data = {}
    # Versions
    data['versions'] = {
        'python': sys.version.split()[0],
        'django': _django_version,
    }
    # Optional: Bokeh version
    try:
        import bokeh  # type: ignore
        data['versions']['bokeh'] = getattr(bokeh, '__version__', None) or ''
    except Exception:
        data['versions']['bokeh'] = None
    # Settings of interest
    try:
        from django.conf import settings
        data['celery'] = {
            'broker_url': getattr(settings, 'CELERY_BROKER_URL', ''),
            'result_backend': getattr(settings, 'CELERY_RESULT_BACKEND', ''),
            'task_always_eager': bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)),
        }
        data['features'] = {
            'fs_reconcile_enabled': bool(getattr(settings, 'ENABLE_FS_RECONCILE', False)),
            'download_cleanup_enabled': bool(getattr(settings, 'ENABLE_DOWNLOAD_CLEANUP', False)),
        }
    except Exception:
        data['celery'] = {}
        data['features'] = {}

    # DB health
    db_ok = False
    db_latency_ms = None
    try:
        t0 = _time.time()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        db_latency_ms = int((_time.time() - t0) * 1000)
        db_ok = True
    except Exception as e:
        data['db_error'] = str(e)
    data['database'] = {'ok': db_ok, 'latency_ms': db_latency_ms}

    # Celery worker ping
    worker_ok = False
    workers = []
    try:
        if celery_app:
            insp = celery_app.control.inspect(timeout=1.0)
            pong = insp.ping() or {}
            workers = list(pong.keys())
            worker_ok = len(workers) > 0
    except Exception as e:
        data['celery_ping_error'] = str(e)
    data['celery']['workers'] = workers
    data['celery']['workers_alive'] = worker_ok

    # Redis (broker) ping
    redis_ok = None
    redis_latency_ms = None
    try:
        broker = data['celery'].get('broker_url') or ''
        if broker.startswith('redis') and _redis:
            # Parse redis URL
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            t0 = _time.time()
            pong = client.ping()
            redis_latency_ms = int((_time.time() - t0) * 1000)
            redis_ok = bool(pong)
    except Exception as e:
        data['redis_error'] = str(e)
    data['redis'] = {'ok': redis_ok, 'latency_ms': redis_latency_ms}

    # Storage (filesystem) stats for data path
    storage = {'ok': None}
    try:
        import environ
        env = environ.Env()
        environ.Env.read_env()
        data_path = env('DATA_DIRECTORY', default='/archive/ftp/')
        p = Path(data_path)
        exists = p.exists()
        storage['path'] = str(p)
        storage['exists'] = exists
        if exists:
            st = os.statvfs(str(p))
            total = st.f_frsize * st.f_blocks
            free = st.f_frsize * st.f_bavail
            used = total - free
            storage.update({
                'total_bytes': total,
                'used_bytes': used,
                'free_bytes': free,
            })
            storage['ok'] = True
        else:
            storage['ok'] = False
    except Exception as e:
        storage['ok'] = False
        storage['error'] = str(e)
    data['storage'] = storage

    # Periodic task last runs (from Redis heartbeat written by tasks)
    periodic = {}
    try:
        broker = data.get('celery', {}).get('broker_url') or ''
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            for name in ['cleanup_expired_downloads', 'reconcile_filesystem', 'cleanup_orphans_hashcheck']:
                hk = f'health:task:{name}'
                last_run = client.hget(hk, 'last_run')
                last_error = client.hget(hk, 'last_error')
                data_json = client.hget(hk, 'data')
                entry = {}
                if last_run:
                    try:
                        s = last_run.decode('utf-8')
                        entry['last_run'] = s
                        try:
                            from django.utils.dateparse import parse_datetime
                            dt = parse_datetime(s)
                            if dt is not None:
                                age = (timezone.now() - dt).total_seconds()
                                entry['age_seconds'] = int(age)
                        except Exception:
                            pass
                    except Exception:
                        pass
                if last_error:
                    try:
                        entry['last_error'] = last_error.decode('utf-8')
                    except Exception:
                        entry['last_error'] = str(last_error)
                if data_json:
                    try:
                        entry['data'] = json.loads(data_json.decode('utf-8'))
                    except Exception:
                        pass
                periodic[name] = entry
    except Exception as e:
        data['periodic_error'] = str(e)
    data['periodic'] = periodic

    # Extra settings surface
    try:
        data['settings'] = {
            'DOWNLOAD_JOB_TTL_HOURS': int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72)),
            'DATA_DIRECTORY': os.environ.get('DATA_DIRECTORY', ''),
            'WATCH_DEBOUNCE_SECONDS': os.environ.get('WATCH_DEBOUNCE_SECONDS', ''),
            'WATCH_CREATED_DELAY_SECONDS': os.environ.get('WATCH_CREATED_DELAY_SECONDS', ''),
            'WATCH_STABILITY_SECONDS': os.environ.get('WATCH_STABILITY_SECONDS', ''),
            'SIMBAD_MIN_INTERVAL': os.environ.get('SIMBAD_MIN_INTERVAL', ''),
        }
    except Exception:
        data['settings'] = {}

    # LDAP status
    ldap_info = {'configured': False}
    try:
        server_uri = getattr(settings, 'AUTH_LDAP_SERVER_URI', None) or os.environ.get('LDAP_SERVER_URI')
        if server_uri:
            ldap_info['configured'] = True
            ldap_info['server_uri'] = server_uri
            ldap_info['can_import'] = bool(_ldap is not None)
            if _ldap:
                # Initialize and optional StartTLS
                start_tls = bool(getattr(settings, 'AUTH_LDAP_START_TLS', False) or str(os.environ.get('LDAP_START_TLS', 'false')).lower() in ('1','true','yes'))
                bind_dn = getattr(settings, 'AUTH_LDAP_BIND_DN', None) or os.environ.get('LDAP_BIND_DN') or ''
                bind_pw = getattr(settings, 'AUTH_LDAP_BIND_PASSWORD', None) or os.environ.get('LDAP_BIND_PASSWORD') or ''
                try:
                    conn = _ldap.initialize(server_uri)
                    conn.set_option(_ldap.OPT_REFERRALS, 0)
                    if start_tls:
                        try:
                            conn.start_tls_s()
                            ldap_info['start_tls'] = True
                        except Exception as e:
                            ldap_info['start_tls'] = False
                            ldap_info['tls_error'] = str(e)
                    # Anonymous bind if no DN provided
                    try:
                        if bind_dn:
                            conn.simple_bind_s(bind_dn, bind_pw or '')
                        else:
                            conn.simple_bind_s()
                        ldap_info['bind_ok'] = True
                    except Exception as e:
                        ldap_info['bind_ok'] = False
                        ldap_info['bind_error'] = str(e)
                    try:
                        conn.unbind_s()
                    except Exception:
                        pass
                except Exception as e:
                    ldap_info['connect_error'] = str(e)
        data['ldap'] = ldap_info
    except Exception as e:
        data['ldap'] = {'configured': False, 'error': str(e)}

    # External services: Aladin reachability
    aladin = {'ok': None}
    try:
        # Use the concrete JS asset that the frontend actually loads
        url = os.environ.get('ALADIN_PING_URL', 'https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js')
        t0 = _time.time()
        status = None
        # Try requests first
        try:
            import requests  # type: ignore
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; OSTdata/health-check)'}
            # Prefer GET because some servers return 403 to HEAD; use stream to avoid downloading content
            r = requests.get(url, timeout=3.0, allow_redirects=True, headers=headers, stream=True)
            try:
                status = r.status_code
            finally:
                try:
                    r.close()
                except Exception:
                    pass
        except Exception:
            # Fallback to urllib
            try:
                import urllib.request  # type: ignore
                req = urllib.request.Request(url, method='GET', headers={'User-Agent': 'Mozilla/5.0 (compatible; OSTdata/health-check)'})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    status = getattr(resp, 'status', 200)
            except Exception as e2:
                aladin['error'] = str(e2)
        latency_ms = int((_time.time() - t0) * 1000)
        aladin['latency_ms'] = latency_ms
        if status is not None:
            aladin['status_code'] = int(status)
            aladin['ok'] = 200 <= int(status) < 400
        else:
            aladin['ok'] = False
    except Exception as e:
        aladin['ok'] = False
        aladin['error'] = str(e)
    data['aladin'] = aladin

    # Optional system resources if psutil available
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        sysinfo = {
            'cpu_percent': float(cpu),
            'memory': {
                'total_bytes': int(vm.total),
                'used_bytes': int(vm.total - vm.available),
                'free_bytes': int(vm.available),
                'percent': float(vm.percent),
            }
        }
        # Try overall disk usage at root (can be adjusted via env if needed)
        try:
            root_path = os.environ.get('SYSTEM_DISK_PATH', '/') or '/'
            du = psutil.disk_usage(root_path)
            sysinfo['disk'] = {
                'path': root_path,
                'total_bytes': int(du.total),
                'used_bytes': int(du.used),
                'free_bytes': int(du.free),
                'percent': float(du.percent),
            }
        except Exception:
            pass
        data['system'] = sysinfo
    except Exception:
        data['system'] = None

    # Download job stats
    try:
        counts = {}
        for s in ['queued', 'running', 'done', 'failed', 'cancelled', 'expired']:
            counts[s] = DownloadJob.objects.filter(status=s).count()
        data['jobs'] = counts
    except Exception as e:
        data['jobs_error'] = str(e)

    return Response(data, status=200)


# ===============================================================
#   ADMIN - SITE-WIDE BANNER (maintenance notice)
# ===============================================================

_BANNER_REDIS_KEY = 'site:banner'

def _get_redis_from_broker():
    try:
        from django.conf import settings
        broker = getattr(settings, 'CELERY_BROKER_URL', '')
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            return client
    except Exception:
        pass
    return None

def _banner_get():
    client = _get_redis_from_broker()
    if not client:
        return None
    try:
        raw = client.get(_BANNER_REDIS_KEY)
        if not raw:
            return None
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return None
    except Exception:
        return None

def _banner_set(payload: dict):
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.set(_BANNER_REDIS_KEY, json.dumps(payload))
        return True
    except Exception:
        return False

def _banner_clear():
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.delete(_BANNER_REDIS_KEY)
        return True
    except Exception:
        return False

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_banner(request):
    """
    Get current site-wide banner.
    Returns: { enabled: bool, message: str, level: 'info'|'success'|'warning'|'error' }
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    data = _banner_get() or {'enabled': False, 'message': '', 'level': 'warning'}
    return Response(data)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_set_banner(request):
    """
    Set site-wide banner.
    Body: { enabled: bool, message: str, level: 'info'|'success'|'warning'|'error' }
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    body = request.data if hasattr(request, 'data') else {}
    enabled = bool(body.get('enabled', True))
    message = str(body.get('message', '') or '')
    level = str(body.get('level', 'warning') or 'warning')
    payload = {'enabled': enabled, 'message': message, 'level': level}
    ok = _banner_set(payload)
    if not ok:
        return Response({'error': 'Failed to persist banner'}, status=500)
    return Response(payload)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_clear_banner(request):
    """
    Clear site-wide banner.
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    ok = _banner_clear()
    if not ok:
        return Response({'error': 'Failed to clear banner'}, status=500)
    return Response({'cleared': True})

@api_view(['GET'])
@permission_classes([AllowAny])
def banner_info(request):
    """
    Public endpoint: Get current site-wide banner (read-only).
    Returns: { enabled, message, level }
    """
    data = _banner_get() or {'enabled': False, 'message': '', 'level': 'warning'}
    return Response(data)
