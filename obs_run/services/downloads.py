"""Download job enqueue, token, and quota helpers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import PermissionDenied, ValidationError

from obs_run.datafile_filters import apply_datafile_filters
from obs_run.models import DataFile, DownloadJob, ObservationRun
from obs_run.tasks import build_zip_task
from ostdata.custom_permissions import get_allowed_run_objects_to_view_for_user

try:
    import redis as _redis
except Exception:  # pragma: no cover
    _redis = None


@dataclass
class EnqueuedJob:
    id: int
    status: str
    job_token: Optional[str] = None


class DownloadQuotaExceeded(ValidationError):
    pass


def hash_download_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def verify_download_token(job: DownloadJob, token: Optional[str]) -> bool:
    if not token or not job.access_token_hash:
        return False
    digest = hash_download_token(token)
    return hmac.compare_digest(digest, job.access_token_hash)


def _client_ip_bucket(request) -> str:
    """Pseudonymized IP bucket for anonymous quotas (never store raw IPs)."""
    if request is None:
        return 'unknown'
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')[0].strip()
    ip = forwarded or request.META.get('REMOTE_ADDR') or 'unknown'
    salt = getattr(settings, 'SECRET_KEY', 'ostdata')[:32]
    return hashlib.sha256(f'{salt}:{ip}'.encode('utf-8')).hexdigest()[:32]


def _redis_client():
    broker = getattr(settings, 'CELERY_BROKER_URL', '') or ''
    if not broker.startswith('redis') or not _redis:
        return None
    try:
        u = urlparse(broker)
        host = u.hostname or '127.0.0.1'
        port = int(u.port or 6379)
        db = int((u.path or '/0').lstrip('/') or 0)
        password = u.password
        return _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
    except Exception:
        return None


def _active_job_qs():
    return DownloadJob.objects.filter(status__in=('queued', 'running'))


def resolve_visible_datafiles(
    user,
    *,
    run: Optional[ObservationRun] = None,
    selected_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
):
    """Materialize the visible DataFile queryset for a download request."""
    from django.contrib.auth.models import AnonymousUser

    if user is None:
        user = AnonymousUser()
    selected_ids = [int(x) for x in (selected_ids or []) if str(x).strip().lstrip('-').isdigit()]
    filters = dict(filters or {})
    qs = DataFile.objects.all().select_related('observation_run')
    if run is not None:
        qs = qs.filter(observation_run_id=run.pk)
    qs = get_allowed_run_objects_to_view_for_user(qs, user)
    if selected_ids:
        qs = qs.filter(pk__in=selected_ids)
    elif not filters:
        # Empty bulk selection must not archive the whole catalog.
        if run is None:
            raise ValidationError({'detail': 'ids or filters required for bulk download'})
    qs = apply_datafile_filters(qs, filters)
    return qs


def enforce_download_quotas(user, request, qs) -> List[int]:
    """Validate file count/bytes and concurrent job limits. Returns materialized PKs."""
    from django.contrib.auth.models import AnonymousUser

    if user is None:
        user = AnonymousUser()
    pks = list(qs.values_list('pk', flat=True))
    max_files = int(getattr(settings, 'DOWNLOAD_JOB_MAX_FILES', 500))
    max_bytes = int(getattr(settings, 'DOWNLOAD_JOB_MAX_BYTES', 10 * 1024 ** 3))
    if not pks:
        raise ValidationError({'detail': 'No files to include'})
    if len(pks) > max_files:
        raise DownloadQuotaExceeded({'detail': f'Too many files (max {max_files})'})

    total_bytes = (
        DataFile.objects.filter(pk__in=pks)
        .aggregate(total=Sum('file_size'))
        .get('total')
        or 0
    )
    # Fallback: count unknown sizes as zero but still enforce file count
    if total_bytes and total_bytes > max_bytes:
        raise DownloadQuotaExceeded({'detail': f'Total size exceeds limit ({max_bytes} bytes)'})

    authed = bool(user and getattr(user, 'is_authenticated', False))
    max_user = int(getattr(settings, 'DOWNLOAD_JOB_MAX_CONCURRENT_USER', 5))
    max_anon = int(getattr(settings, 'DOWNLOAD_JOB_MAX_CONCURRENT_ANON', 2))
    max_global = int(getattr(settings, 'DOWNLOAD_JOB_MAX_CONCURRENT_GLOBAL', 20))

    if _active_job_qs().count() >= max_global:
        raise DownloadQuotaExceeded({'detail': 'Too many active download jobs globally'})

    if authed:
        if _active_job_qs().filter(user_id=user.pk).count() >= max_user:
            raise DownloadQuotaExceeded({'detail': 'Too many active download jobs for this user'})
    else:
        # Approximate anon concurrency via Redis create counters + DB null-user active jobs
        if _active_job_qs().filter(user__isnull=True).count() >= max_anon * 5:
            raise DownloadQuotaExceeded({'detail': 'Too many active anonymous download jobs'})

    # Hourly create rate via Redis when available
    client = _redis_client()
    if client is not None:
        try:
            if authed:
                key = f'dl_create:user:{user.pk}'
                limit = int(getattr(settings, 'DOWNLOAD_JOB_MAX_CREATES_PER_HOUR_USER', 30))
            else:
                key = f'dl_create:ip:{_client_ip_bucket(request)}'
                limit = int(getattr(settings, 'DOWNLOAD_JOB_MAX_CREATES_PER_HOUR_ANON', 10))
            count = client.incr(key)
            if count == 1:
                client.expire(key, 3600)
            if count > limit:
                raise DownloadQuotaExceeded({'detail': 'Download create rate limit exceeded'})
            if not authed:
                anon_key = f'dl_active_anon:{_client_ip_bucket(request)}'
                active = int(client.get(anon_key) or 0)
                if active >= max_anon:
                    raise DownloadQuotaExceeded({'detail': 'Too many concurrent anonymous downloads'})
                client.incr(anon_key)
                client.expire(anon_key, 3600)
        except DownloadQuotaExceeded:
            raise
        except Exception:
            pass

    return pks


def enqueue_download_job_for_run(
    run: ObservationRun,
    user,
    selected_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
    request=None,
) -> EnqueuedJob:
    qs = resolve_visible_datafiles(
        user,
        run=run,
        selected_ids=selected_ids,
        filters=filters,
    )
    pks = enforce_download_quotas(user, request, qs)
    return _create_job(user=user, run=run, selected_ids=pks, filters=filters or {}, reason='api:download_job_create')


def enqueue_download_job_bulk(
    user,
    selected_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
    request=None,
) -> EnqueuedJob:
    qs = resolve_visible_datafiles(
        user,
        run=None,
        selected_ids=selected_ids,
        filters=filters,
    )
    pks = enforce_download_quotas(user, request, qs)
    return _create_job(user=user, run=None, selected_ids=pks, filters=filters or {}, reason='api:download_job_create_bulk')


def _create_job(*, user, run, selected_ids, filters, reason) -> EnqueuedJob:
    authed = bool(user and getattr(user, 'is_authenticated', False))
    token = None
    token_hash = ''
    if not authed:
        token = secrets.token_urlsafe(32)
        token_hash = hash_download_token(token)

    with transaction.atomic():
        job = DownloadJob.objects.create(
            user=user if authed else None,
            run=run,
            selected_ids=list(selected_ids),
            filters=dict(filters or {}),
            status='queued',
            access_token_hash=token_hash,
        )
    build_zip_task.delay(job.pk)
    try:
        from adminops.audit_events import log_download_job_event
        log_download_job_event(
            job,
            action='created',
            change_reason=reason,
            user=user if authed else None,
            summary=f'Download job queued ({len(selected_ids)} file id(s))',
        )
    except Exception:
        pass
    return EnqueuedJob(id=job.pk, status=job.status, job_token=token)


def user_can_access_download_job(request, job: DownloadJob) -> bool:
    """Authorize status/cancel/download: owner, admin ACL, or anonymous token."""
    user = getattr(request, 'user', None)
    if user and getattr(user, 'is_authenticated', False):
        if getattr(user, 'is_superuser', False):
            return True
        try:
            if user.has_perm('users.acl_jobs_view_all') or user.has_perm('users.acl_jobs_cancel_any'):
                return True
        except Exception:
            pass
        if job.user_id and job.user_id == user.pk:
            return True
        # Authenticated user accessing anonymous job still needs token
    token = request.headers.get('X-Download-Token') or request.META.get('HTTP_X_DOWNLOAD_TOKEN')
    if job.user_id is None and verify_download_token(job, token):
        return True
    return False


def require_download_job_access(request, job: DownloadJob) -> None:
    if not user_can_access_download_job(request, job):
        raise PermissionDenied('Not found')
