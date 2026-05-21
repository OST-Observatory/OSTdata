"""
Write explicit audit log entries and resolve the acting user when possible.
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model

from adminops.models import AuditLogEntry

User = get_user_model()

MODEL_LABELS = {
    'acl': 'ACL',
    'banner': 'Banner',
    'download_job': 'Download job',
    'solar_image': 'Solar image',
    'tag_assignment': 'Tag assignment',
    'user_role': 'User',
}


def get_audit_user():
    """Best-effort current user (API requests via simple_history middleware)."""
    try:
        from simple_history.middleware import HistoricalRecords

        req = getattr(HistoricalRecords.thread, 'request', None)
        if req and getattr(req.user, 'is_authenticated', False):
            return req.user
    except Exception:
        pass
    return None


def download_job_entity_label(job) -> str:
    run = getattr(job, 'run', None)
    if run is not None:
        run_name = getattr(run, 'name', None) or f'run #{job.run_id}'
        return f'Download job #{job.pk} ({run_name})'
    return f'Download job #{job.pk} (bulk)'


def log_download_job_event(
    job,
    *,
    action: str,
    change_reason: str,
    user=None,
    summary: str = '',
) -> AuditLogEntry | None:
    try:
        entity_path = '/admin/jobs'
        if getattr(job, 'run_id', None):
            entity_path = f'/observation-runs/{job.run_id}'
        return log_audit_event(
            model_type='download_job',
            action=action,
            entity_label=download_job_entity_label(job),
            entity_path=entity_path,
            change_reason=change_reason,
            user=user,
            instance_id=job.pk,
            summary=summary or f'Download job {action}',
        )
    except Exception:
        return None


def log_audit_event(
    *,
    model_type: str,
    action: str,
    entity_label: str,
    entity_path: str = '',
    change_reason: str = '',
    user=None,
    instance_id: int | None = None,
    changes: list[dict[str, Any]] | None = None,
    summary: str = '',
    is_batch: bool = False,
    batch_count: int = 1,
) -> AuditLogEntry:
    actor = user if user is not None else get_audit_user()
    return AuditLogEntry.objects.create(
        model_type=model_type,
        model_label=MODEL_LABELS.get(model_type, model_type.replace('_', ' ').title()),
        action=action,
        user=actor,
        instance_id=instance_id,
        entity_label=entity_label[:255],
        entity_path=(entity_path or '')[:255],
        change_reason=(change_reason or '')[:100],
        is_batch=is_batch,
        batch_count=max(1, int(batch_count or 1)),
        changes=changes or [],
        summary=summary or '',
    )
