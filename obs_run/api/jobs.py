import os
from pathlib import Path
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import serializers
import logging
logger = logging.getLogger(__name__)

try:
    import redis as _redis
except Exception:
    _redis = None

from obs_run.models import ObservationRun, DataFile, DownloadJob
from obs_run.tasks import cleanup_expired_downloads, reconcile_filesystem
from obs_run.tasks import cleanup_orphans_and_hashcheck
from obs_run.services.downloads import enqueue_download_job_for_run, enqueue_download_job_bulk


class DownloadJobBulkRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        default=list,
        help_text="Optional list of DataFile IDs to include",
    )
    filters = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=dict,
        help_text="Optional filter map (keys like file_type, main_target, instrument, etc.)",
    )


class DownloadJobCreateResponseSerializer(serializers.Serializer):
    job_id = serializers.IntegerField()


@extend_schema(
    summary='Create download job (bulk across runs)',
    examples=[
        OpenApiExample(
            'Bulk IDs only',
            value={'ids': [12, 45, 78]},
            request_only=True,
        ),
        OpenApiExample(
            'Filters only',
            value={'filters': {'file_type': 'FITS', 'instrument': 'QHY'}},
            request_only=True,
        ),
        OpenApiExample(
            'Response',
            value={'job_id': 123},
            response_only=True,
        ),
    ],
    tags=['Jobs'],
)
@api_view(['POST'])
def create_download_job_bulk(request):
    """Create a DownloadJob for arbitrary datafiles (IDs and/or filters across runs)."""
    payload = request.data if hasattr(request, 'data') else {}
    selected_ids = payload.get('ids') or []
    filters = payload.get('filters') or {}
    job = enqueue_download_job_bulk(
        user=request.user if request.user.is_authenticated else None,
        selected_ids=selected_ids,
        filters=filters,
    )
    return Response({'job_id': job.id}, status=201)

create_download_job_bulk.throttle_classes = [ScopedRateThrottle]
create_download_job_bulk.throttle_scope = 'jobs'
create_download_job_bulk.__dict__['extend_schema'] = extend_schema(
    request=DownloadJobBulkRequestSerializer,
    responses=DownloadJobCreateResponseSerializer,
)(create_download_job_bulk)

class RunDownloadJobRequestSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        default=list,
    )
    filters = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=dict,
    )


@extend_schema(
    summary='Create download job for a specific run',
    request=RunDownloadJobRequestSerializer,
    responses=DownloadJobCreateResponseSerializer,
    tags=['Jobs'],
)
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
    job = enqueue_download_job_for_run(
        run=run,
        user=request.user if request.user.is_authenticated else None,
        selected_ids=selected_ids,
        filters=filters,
    )
    return Response({'job_id': job.id}, status=201)

create_download_job.throttle_classes = [ScopedRateThrottle]
create_download_job.throttle_scope = 'jobs'

@extend_schema(summary='Get download job status')
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


@extend_schema(
    summary='List download jobs (admin sees all)',
    parameters=[
        OpenApiParameter('status', str, OpenApiParameter.QUERY, description='Filter by status (queued|running|done|failed|cancelled|expired)'),
        OpenApiParameter('run', int, OpenApiParameter.QUERY, description='Filter by run ID'),
        OpenApiParameter('user', int, OpenApiParameter.QUERY, description='Filter by user ID (admin/staff only)'),
    ],
    tags=['Jobs'],
)
@api_view(['GET'])
def list_download_jobs(request):
    """List download jobs. Admins see all; authenticated users see their own; anonymous see none."""
    qs = DownloadJob.objects.all().order_by('-created_at')
    if request.user.is_authenticated and request.user.is_staff:
        if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_view_all')):
            qs = qs.filter(user_id=request.user.pk)
    elif request.user.is_authenticated:
        qs = qs.filter(user_id=request.user.pk)
    else:
        qs = qs.none()
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


@extend_schema(summary='Cancel a download job')
@api_view(['POST'])
def cancel_download_job(request, job_id):
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        return Response({'detail': 'Not found'}, status=404)
    is_admin = bool(getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False))
    if job.user_id and (not request.user.is_authenticated or (request.user.pk != job.user_id and not is_admin)):
        return Response({'detail': 'Not found'}, status=404)
    if is_admin and job.user_id and request.user.pk != job.user_id:
        if not (request.user.is_superuser or request.user.has_perm('users.acl_jobs_cancel_any')):
            return Response({'detail': 'Forbidden'}, status=403)
    if job.status in ('done', 'failed', 'cancelled', 'expired'):
        return Response({'status': job.status, 'error': job.error or ''})
    job.status = 'cancelled'
    job.finished_at = timezone.now()
    try:
        actor = 'administrator' if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False) else 'user'
        msg = f'Cancelled by {actor}'
        try:
            from datetime import timedelta
            from django.conf import settings
            ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
        except Exception:
            ttl_hours = 72
        job.expires_at = job.finished_at + timedelta(hours=ttl_hours)
        if not job.error:
            job.error = msg
        else:
            job.error = f'{job.error} (cancelled by {actor})'
        job.save(update_fields=['status', 'finished_at', 'expires_at', 'error'])
    except Exception:
        job.save(update_fields=['status', 'finished_at'])
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
    except Exception as e:
        logger.warning("Failed to set cancel flag for job %s: %s", job.pk, e)
    return Response({'status': job.status, 'error': job.error or ''})


@extend_schema(summary='Batch cancel download jobs (admin)')
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
    except Exception as e:
        logger.warning("Failed to set batch cancel flags: %s", e)
    return Response({'cancelled': cancelled, 'skipped': skipped}, status=200)


@extend_schema(summary='Batch extend download job expiry (admin)')
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


@extend_schema(summary='Batch expire download jobs immediately (admin)')
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


@extend_schema(summary='Download ZIP file for a completed job')
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


