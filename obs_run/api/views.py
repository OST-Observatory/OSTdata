from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from obs_run.models import ObservationRun, DataFile

from .serializers import DataFileSerializer
from .filter import DataFileFilter
from utilities import annotate_effective_exposure_type

from django.http import HttpResponse
from io import BytesIO
from pathlib import Path
import tempfile
import zipfile
import numpy as np
from astropy.io import fits
from astropy.visualization import ZScaleInterval, ImageNormalize, AsinhStretch
try:
    from PIL import Image
except Exception:
    Image = None

from drf_spectacular.utils import extend_schema, OpenApiParameter, extend_schema_view
import logging
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
)
@api_view(['GET'])
def get_datafile_thumbnail(request, pk):
    """
    Return a PNG thumbnail for the given DataFile.
    FITS uses ZScale + asinh stretch; JPG/TIFF are thumbnailed directly.
    Videos (SER/AVI/MOV) are not supported for thumbnail generation.
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
    # Treat video-like types as unsupported for thumbnails
    is_video = (file_type in ('SER', 'AVI', 'MOV')) or (file_path.suffix.lower() in ['.ser', '.avi', '.mov'])

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
        elif is_video:
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
        return Response({"detail": str(e)}, status=400)


@extend_schema(summary='DataFile FITS header', parameters=[OpenApiParameter('pk', int, OpenApiParameter.PATH)])
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
        logger.exception("header read failed for datafile %s: %s", pk, e)
        return Response({"detail": str(e)}, status=400)


@extend_schema(summary='Download raw datafile', parameters=[OpenApiParameter('pk', int, OpenApiParameter.PATH)])
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
        logger.exception("download failed for datafile %s: %s", pk, e)
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
        # Use effective exposure type for filtering
        qs = annotate_effective_exposure_type(qs)
        qs = qs.filter(effective_exposure_type__in=q_params.getlist('exposure_type'))
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
        logger.exception("run ZIP creation failed for run %s: %s", run_pk, e)
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
        # Use effective exposure type for filtering
        qs = annotate_effective_exposure_type(qs)
        qs = qs.filter(effective_exposure_type__in=q_params.getlist('exposure_type'))
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
        logger.exception("bulk ZIP creation failed: %s", e)
        return Response({"detail": str(e)}, status=400)


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

#
# Dashboard stats moved to .runs
#

#
# Download job endpoints moved to .jobs
#

#
# Admin endpoints moved to adminops app
#

