from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from django.db import transaction
from django.utils import timezone

from obs_run.models import ObservationRun, DownloadJob
from obs_run.tasks import build_zip_task


@dataclass
class EnqueuedJob:
    id: int
    status: str


def enqueue_download_job_for_run(
    run: ObservationRun,
    user,
    selected_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> EnqueuedJob:
    selected_ids = list(selected_ids or [])
    filters = dict(filters or {})
    with transaction.atomic():
        job = DownloadJob.objects.create(
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            run=run,
            selected_ids=selected_ids,
            filters=filters,
            status='queued',
        )
    build_zip_task.delay(job.pk)
    return EnqueuedJob(id=job.pk, status=job.status)


def enqueue_download_job_bulk(
    user,
    selected_ids: Optional[Iterable[int]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> EnqueuedJob:
    selected_ids = list(selected_ids or [])
    filters = dict(filters or {})
    job = DownloadJob.objects.create(
        user=user if (user and getattr(user, 'is_authenticated', False)) else None,
        run=None,
        selected_ids=selected_ids,
        filters=filters,
        status='queued',
    )
    build_zip_task.delay(job.pk)
    return EnqueuedJob(id=job.pk, status=job.status)


