from io import BytesIO
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.visualization import AsinhStretch, ImageNormalize, ZScaleInterval
from django.conf import settings as django_settings
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from obs_run.models import DataFile, ObservationRun
from obs_run.ser_thumbnails import get_ser_thumbnail_png, is_ser_path
from ostdata.custom_permissions import get_allowed_run_objects_to_view_for_user
from ostdata.permissions import user_has_acl

from .filter import DataFileFilter
from .serializers import DataFileSerializer

try:
    from PIL import Image
except Exception:
    Image = None

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view

from ostdata.openapi import JSON_OBJECT_RESPONSE

logger = logging.getLogger(__name__)
#


#
# OBSERVATION RUNS moved to .runs
#



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


@extend_schema(
    summary='DataFile thumbnail',
    parameters=[
        OpenApiParameter('pk', int, OpenApiParameter.PATH),
        OpenApiParameter('w', int, OpenApiParameter.QUERY, description='Max width/height in pixels (default 512, max 2048)'),
    ],
    responses={200: OpenApiTypes.BINARY},
)
@api_view(['GET'])
def get_datafile_thumbnail(request, pk):
    """
    Return a PNG thumbnail for the given DataFile.
    FITS uses ZScale + asinh stretch; JPG/TIFF are thumbnailed directly.
    SER extracts a representative frame (cached on disk). AVI/MOV are not supported.
    Optional query params: w (int, default 512)
    """
    try:
        df = DataFile.objects.select_related('observation_run').get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    run = df.observation_run
    if request.user.is_anonymous:
        if run and not run.is_public:
            return Response({"detail": "Not found"}, status=404)
    elif run and not run.is_public:
        try:
            if not request.user.can_read(run):
                return Response({"detail": "Not found"}, status=404)
        except Exception:
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

    try:
        from obs_run.services.datafile_paths import PathOutsideDataRoot, safe_datafile_path
        file_path = safe_datafile_path(df.datafile, must_exist=True)
    except PathOutsideDataRoot:
        return Response({"detail": "File not found"}, status=404)
    except FileNotFoundError:
        return Response({"detail": "File not found"}, status=404)

    try:
        max_source = int(getattr(django_settings, 'THUMBNAIL_MAX_SOURCE_BYTES', 500 * 1024 * 1024))
        if file_path.stat().st_size > max_source:
            return Response({"detail": "Source file too large for thumbnail"}, status=400)
    except Exception:
        pass

    file_type = (df.file_type or '').upper()

    # Determine FITS by type or extension (fallback)
    is_fits = (file_type == 'FITS') or (file_path.suffix.lower() in ['.fits', '.fit', '.fts'])
    is_ser = is_ser_path(file_type, file_path)
    is_other_video = (file_type in ('AVI', 'MOV')) or (file_path.suffix.lower() in ['.avi', '.mov'])

    try:
        if is_ser:
            png = get_ser_thumbnail_png(
                datafile_id=df.pk,
                content_hash=df.content_hash or '',
                file_path=file_path,
                max_dim=w,
            )
            return HttpResponse(png, content_type='image/png')
        # FITS handling with zscale
        if is_fits:
            # Some FITS with BZERO/BSCALE/BLANK cannot be memory-mapped; disable memmap
            with fits.open(str(file_path), memmap=False) as hdul:
                data = None
                # Prefer first image-like HDU with 2D data
                for hdu in hdul:
                    hdu_data = getattr(hdu, 'data', None)
                    if hdu_data is not None:
                        arr = np.asarray(hdu_data)
                        if arr.ndim >= 2:
                            data = arr
                            break
                if data is None:
                    return Response({"detail": "No image data"}, status=400)
                if data.ndim > 2:
                    data = data[0]
                max_pixels = int(getattr(django_settings, 'THUMBNAIL_MAX_PIXELS', 50_000_000))
                if int(np.prod(data.shape)) > max_pixels:
                    return Response({"detail": "Image too large for thumbnail"}, status=400)
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
        elif is_other_video:
            return Response({"detail": "Preview not supported for video files"}, status=400)
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
        logger.exception("thumbnail generation failed for datafile %s: %s", pk, e)
        return Response({"detail": "Thumbnail generation failed"}, status=400)


get_datafile_thumbnail.throttle_classes = [ScopedRateThrottle]
get_datafile_thumbnail.throttle_scope = 'thumbnails'


@extend_schema(
    summary='DataFile FITS header',
    parameters=[OpenApiParameter('pk', int, OpenApiParameter.PATH)],
    responses=JSON_OBJECT_RESPONSE,
)
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
    if run and not run.is_public:
        if request.user.is_anonymous:
            return Response({"detail": "Not found"}, status=404)
        try:
            if not request.user.can_read(run):
                return Response({"detail": "Not found"}, status=404)
        except Exception:
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
        logger.exception("header read failed for datafile %s: %s", pk, e)
        return Response({"detail": "Failed to read FITS header"}, status=400)


@extend_schema(
    summary='Download raw datafile',
    operation_id='runs_datafile_download',
    parameters=[OpenApiParameter('pk', int, OpenApiParameter.PATH)],
    responses={200: OpenApiTypes.BINARY},
)
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
    if run and not run.is_public:
        if request.user.is_anonymous:
            return Response({"detail": "Not found"}, status=404)
        try:
            if not request.user.can_read(run):
                return Response({"detail": "Not found"}, status=404)
        except Exception:
            return Response({"detail": "Not found"}, status=404)

    try:
        from obs_run.services.datafile_paths import PathOutsideDataRoot, safe_datafile_path
        file_path = safe_datafile_path(df.datafile, must_exist=True)
    except PathOutsideDataRoot:
        return Response({"detail": "File not found"}, status=404)
    except FileNotFoundError:
        return Response({"detail": "File not found"}, status=404)

    try:
        from django.http import FileResponse
        resp = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=file_path.name)
        return resp
    except Exception as e:
        logger.exception("download failed for datafile %s: %s", pk, e)
        return Response({"detail": "Download failed"}, status=400)


@extend_schema(
    summary='Download run datafiles (retired sync ZIP)',
    responses={410: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
def download_run_datafiles(request, run_pk):
    """Synchronous ZIP downloads are retired; use async download-jobs API."""
    return Response(
        {
            'detail': 'Synchronous ZIP downloads are gone. Use POST /api/runs/runs/{id}/download-jobs/.',
            'code': 'sync_zip_gone',
        },
        status=410,
    )


@extend_schema(
    summary='Download datafiles bulk (retired sync ZIP)',
    operation_id='runs_datafiles_download_bulk',
    responses={410: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
def download_datafiles_bulk(request):
    """Synchronous bulk ZIP downloads are retired; use async download-jobs API."""
    return Response(
        {
            'detail': 'Synchronous ZIP downloads are gone. Use POST /api/runs/datafiles/download-jobs/.',
            'code': 'sync_zip_gone',
        },
        status=410,
    )


#
# Plotting endpoints moved to .runs
#

@api_view(['GET'])
def get_bokeh_version(request):
    """
    DEPRECATED: Bokeh version is surfaced via admin health; frontend loads version from env.
    """
    return Response({ 'version': '' }, status=410)

# ===============================================================
#   DATA FILE
# ===============================================================

@extend_schema_view(
    list=extend_schema(tags=['DataFiles']),
    retrieve=extend_schema(tags=['DataFiles']),
    create=extend_schema(tags=['DataFiles']),
    update=extend_schema(tags=['DataFiles']),
    partial_update=extend_schema(tags=['DataFiles']),
    destroy=extend_schema(tags=['DataFiles']),
)
class DataFileViewSet(viewsets.ModelViewSet):
    """
        Returns a list of all stars/objects in the database
    """
    queryset = DataFile.objects.select_related('observation_run').prefetch_related('object_set').all()
    serializer_class = DataFileSerializer
    pagination_class = DataFilesPagination
    permission_classes = [IsAuthenticatedOrReadOnly]

    filter_backends = (DjangoFilterBackend,)
    filterset_class = DataFileFilter

    def get_queryset(self):
        qs = super().get_queryset()
        return get_allowed_run_objects_to_view_for_user(qs, self.request.user)

    def create(self, request, *args, **kwargs):
        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return Response({'detail': 'Forbidden'}, status=403)
        if not (getattr(user, 'is_superuser', False) or user_has_acl(user, 'acl_runs_edit')):
            return Response({'detail': 'Forbidden'}, status=403)
        run_id = request.data.get('observation_run')
        if run_id is None:
            return Response({'detail': 'observation_run is required'}, status=400)
        try:
            run = ObservationRun.objects.get(pk=run_id)
        except ObservationRun.DoesNotExist:
            return Response({'detail': 'Run not found'}, status=404)
        try:
            if not user.can_add(run):
                return Response({'detail': 'Forbidden'}, status=403)
        except Exception:
            return Response({'detail': 'Forbidden'}, status=403)
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        ordering = request.query_params.get('ordering')
        allowed_sort = [
            'pk', 'datafile', 'observation_run', 'file_type', 'instrument', 'main_target',
            'exposure_type', 'exptime', 'obs_date', 'plate_solved', 'plate_solve_attempted_at',
        ]
        if ordering and ordering.lstrip('-') in allowed_sort:
            queryset = queryset.order_by(ordering, 'pk')

        # Server-side binning filter (derived from FITS header); capped to limit DoS
        binning = request.query_params.get('binning')
        BINNING_HEADER_SCAN_LIMIT = 200
        if binning:
            try:
                target = str(binning).strip().lower()
                ids = []
                for df in queryset.only('pk')[:BINNING_HEADER_SCAN_LIMIT]:
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

#
# Dashboard stats moved to .runs
#

#
# Download job endpoints moved to .jobs
#

#
# Admin endpoints moved to adminops app
#

