from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
import hashlib

from celery import shared_task
import os
import logging
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import json

from obs_run.models import DownloadJob, DataFile, ObservationRun
from utilities import add_new_data_file

logger = logging.getLogger(__name__)

def _health_set(task_key: str, payload: dict):
    """Store periodic task heartbeat info in Redis (when broker is Redis)."""
    try:
        broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('CELERY_BROKER_URL', '')
        if not broker.startswith('redis'):
            return
        try:
            import redis  # type: ignore
        except Exception:
            return
        from urllib.parse import urlparse
        u = urlparse(broker)
        host = u.hostname or '127.0.0.1'
        port = int(u.port or 6379)
        db = int((u.path or '/0').lstrip('/') or 0)
        password = u.password
        client = redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
        key = f'health:task:{task_key}'
        client.hset(key, mapping={
            'last_run': timezone.now().isoformat(),
            'data': json.dumps(payload, default=str),
            'last_error': '',
        })
        # Set a TTL so keys don't linger forever (e.g. 14 days)
        client.expire(key, 14 * 24 * 3600)
    except Exception:
        # Never fail the task because of health bookkeeping
        pass

def _health_error(task_key: str, error: Exception):
    try:
        broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('CELERY_BROKER_URL', '')
        if not broker.startswith('redis'):
            return
        try:
            import redis  # type: ignore
        except Exception:
            return
        from urllib.parse import urlparse
        u = urlparse(broker)
        host = u.hostname or '127.0.0.1'
        port = int(u.port or 6379)
        db = int((u.path or '/0').lstrip('/') or 0)
        password = u.password
        client = redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
        key = f'health:task:{task_key}'
        client.hset(key, mapping={
            'last_run': timezone.now().isoformat(),
            'last_error': str(error),
        })
        client.expire(key, 14 * 24 * 3600)
    except Exception:
        pass

def _get_redis_client():
    """Return a Redis client based on CELERY_BROKER_URL if it's redis://, else None."""
    try:
        broker = getattr(settings, 'CELERY_BROKER_URL', '') or os.environ.get('CELERY_BROKER_URL', '')
        if not broker.startswith('redis'):
            return None
        try:
            import redis  # type: ignore
        except Exception:
            return None
        from urllib.parse import urlparse
        u = urlparse(broker)
        host = u.hostname or '127.0.0.1'
        port = int(u.port or 6379)
        db = int((u.path or '/0').lstrip('/') or 0)
        password = u.password
        return redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
    except Exception:
        return None

def _cancel_key(job_id: int) -> str:
    return f'job_cancel:{job_id}'

def _is_cancelled_flag(job_id: int) -> bool:
    try:
        client = _get_redis_client()
        if not client:
            return False
        return bool(client.exists(_cancel_key(job_id)))
    except Exception:
        return False


@shared_task(bind=True)
def build_zip_task(self, job_id: int):
    """Build a ZIP for a DownloadJob and update its progress fields."""
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
        return

    # If job was cancelled/expired/failed/done before the worker picked it up, do nothing.
    if job.status in ('cancelled', 'expired', 'failed', 'done') or _is_cancelled_flag(job_id):
        return

    job.status = 'running'
    job.started_at = timezone.now()
    job.progress = 0
    job.save(update_fields=['status', 'started_at', 'progress'])

    try:
        qs = DataFile.objects.all().select_related('observation_run')
        if job.run_id:
            qs = qs.filter(observation_run_id=job.run_id)

        # Anonymous jobs: only include files from public runs
        if job.user is None:
            qs = qs.filter(observation_run__is_public=True)

        # Limit to selected ids when provided
        if job.selected_ids:
            ids = []
            for x in job.selected_ids:
                try:
                    ids.append(int(x))
                except Exception:
                    continue
            if ids:
                qs = qs.filter(pk__in=ids)

        # Apply filters
        f = job.filters or {}
        if f.get('file_type'):
            qs = qs.filter(file_type__icontains=f['file_type'])
        if f.get('main_target'):
            from django.db.models import Q
            v = f['main_target']
            qs = qs.filter(Q(main_target__icontains=v) | Q(header_target_name__icontains=v))
        if f.get('exposure_type'):
            qs = qs.filter(exposure_type__in=f['exposure_type'])
        if f.get('spectroscopy') is not None:
            qs = qs.filter(spectroscopy=bool(f['spectroscopy']))
        if f.get('exptime_min') is not None:
            qs = qs.filter(exptime__gte=f['exptime_min'])
        if f.get('exptime_max') is not None:
            qs = qs.filter(exptime__lte=f['exptime_max'])
        if f.get('file_name'):
            qs = qs.filter(datafile__icontains=f['file_name'])
        if f.get('instrument'):
            qs = qs.filter(instrument__icontains=f['instrument'])

        files = list(qs)
        if not files:
            job.status = 'failed'
            job.error = 'No files to include'
            job.finished_at = timezone.now()
            # Set expiry for consistency so cleanup can still sweep this job
            try:
                ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
            except Exception:
                ttl_hours = 72
            job.expires_at = job.finished_at + timedelta(hours=ttl_hours)
            job.save(update_fields=['status', 'error', 'finished_at', 'expires_at'])
            return

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        tmp_path = tmp.name
        tmp.close()

        job.file_path = tmp_path
        job.bytes_total = 0
        job.bytes_done = 0
        job.save(update_fields=['file_path', 'bytes_total', 'bytes_done'])

        # Compute total size and eligible paths
        total = 0
        paths: list[tuple[Path, int]] = []
        for df in files:
            p = Path(df.datafile)
            if p.exists() and p.is_file():
                try:
                    total += p.stat().st_size
                    paths.append((p, df.pk))
                except Exception:
                    continue
        job.bytes_total = total
        job.save(update_fields=['bytes_total'])

        done = 0
        cancelled_midway = False
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p, dfpk in paths:
                # Periodically check if job was cancelled
                try:
                    if _is_cancelled_flag(job.pk):
                        cancelled_midway = True
                        break
                    current_status = DownloadJob.objects.filter(pk=job.pk).values_list('status', flat=True).first()
                    if current_status == 'cancelled':
                        cancelled_midway = True
                        break
                except Exception:
                    pass
                arcname = f"{dfpk}_{p.name}"
                # Stream file into zip to allow responsive cancellation and progress updates
                try:
                    file_size = p.stat().st_size
                except Exception:
                    file_size = None
                try:
                    with p.open('rb') as src, zf.open(arcname, 'w') as dst:
                        CHUNK = 1024 * 1024  # 1 MiB
                        since_update = 0
                        while True:
                            buf = src.read(CHUNK)
                            if not buf:
                                break
                            dst.write(buf)
                            lb = len(buf)
                            done += lb
                            since_update += lb
                            # Periodic status check and progress update
                            if since_update >= (4 * CHUNK) or (total > 0 and done == total):
                                try:
                                    if _is_cancelled_flag(job.pk):
                                        cancelled_midway = True
                                        break
                                    current_status = DownloadJob.objects.filter(pk=job.pk).values_list('status', flat=True).first()
                                    if current_status == 'cancelled':
                                        cancelled_midway = True
                                        break
                                    if total > 0:
                                        prog = int(min(100, max(0, round(done * 100 / total))))
                                        DownloadJob.objects.filter(pk=job.pk).update(bytes_done=done, progress=prog)
                                except Exception:
                                    pass
                                since_update = 0
                    if cancelled_midway:
                        break
                    # Final progress update after finishing this file
                    if total > 0:
                        try:
                            prog = int(min(100, max(0, round(done * 100 / total))))
                            DownloadJob.objects.filter(pk=job.pk).update(bytes_done=done, progress=prog)
                        except Exception:
                            pass
                except Exception:
                    # Skip unreadable/failed file but continue others
                    continue

        # If cancelled during processing, cleanup and do not override cancelled status
        if cancelled_midway:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            # Clear file_path to avoid dangling partial archives
            try:
                job = DownloadJob.objects.get(pk=job_id)
                job.file_path = ''
                job.finished_at = job.finished_at or timezone.now()
                # Preserve cancelled status set by API
                job.save(update_fields=['file_path', 'finished_at'])
            except Exception:
                pass
            return

        # Before marking as done, re-check that job was not cancelled in the meantime
        try:
            job = DownloadJob.objects.get(pk=job_id)
            if job.status in ('cancelled', 'expired', 'failed'):
                # Do not override terminal status
                return
        except DownloadJob.DoesNotExist:
            return

        job.status = 'done'
        job.progress = 100
        job.bytes_done = done
        job.finished_at = timezone.now()
        # Set expiry time for cleanup
        try:
            ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
        except Exception:
            ttl_hours = 72
        job.expires_at = job.finished_at + timedelta(hours=ttl_hours)
        job.save(update_fields=['status', 'progress', 'bytes_done', 'finished_at', 'expires_at'])
    except Exception as e:
        # On unexpected failure, also set an expiry to allow cleanup
        try:
            ttl_hours = int(getattr(settings, 'DOWNLOAD_JOB_TTL_HOURS', 72))
        except Exception:
            ttl_hours = 72
        finished = timezone.now()
        expires = finished + timedelta(hours=ttl_hours)
        DownloadJob.objects.filter(pk=job.pk).update(status='failed', error=str(e), finished_at=finished, expires_at=expires)


@shared_task(bind=True)
def reconcile_filesystem(self, dry_run: bool = False):
    """Reconcile DB paths with the filesystem layout.
    - Verifies that DataFile paths for each ObservationRun start with the expected
      base directory + run name prefix. If not, attempts to rewrite the prefix
      to match the current run name when the file exists there.
    - Logs missing run directories and counts of updated paths.
    """
    base = (
        os.environ.get('DATA_DIRECTORY')
        or os.environ.get('DATA_PATH')
        or '/archive/ftp/'
    )
    if not base.endswith(os.sep):
        base = base + os.sep

    try:
        dirnames = set()
        with os.scandir(base) as it:
            for entry in it:
                if entry.is_dir():
                    dirnames.add(entry.name)
    except Exception as e:
        logger.error("Reconcile: failed to scan base directory %s: %s", base, e)
        return {'updated': 0, 'runs_missing': 0}

    updated = 0
    runs_missing = 0
    files_checked = 0
    already_ok = 0
    prefix_rewrites = 0
    hash_recoveries = 0
    ambiguous_matches = 0
    recovery_failures = 0
    for run in ObservationRun.objects.all():
        expected_prefix = os.path.join(base, run.name) + os.sep
        if run.name not in dirnames:
            runs_missing += 1
            logger.warning("Reconcile: run directory missing for '%s' under %s", run.name, base)

        # Iterate files for this run
        for df in DataFile.objects.filter(observation_run=run).only('pk', 'datafile', 'content_hash', 'file_size'):
            try:
                p = str(df.datafile)
                files_checked += 1
                # Quick check: if already correct, skip
                if p.startswith(expected_prefix):
                    already_ok += 1
                    continue
                # Attempt to build a corrected path by keeping subpath after top-level segment
                if p.startswith(base):
                    rel = p[len(base):].lstrip(os.sep)
                    parts = rel.split(os.sep)
                    if parts:
                        rest = parts[1:]  # drop old top-level folder
                        candidate = os.path.join(expected_prefix, *rest) if rest else expected_prefix[:-1]
                        if os.path.exists(candidate):
                            if not dry_run:
                                df.datafile = candidate
                                df.save(update_fields=['datafile'])
                            updated += 1
                            prefix_rewrites += 1
                        else:
                            # Try hash-based recovery: scan candidate dir for same-size+hash file
                            try:
                                if df.content_hash:
                                    target_dir = expected_prefix
                                    matches = []
                                    for root, dirs, files in os.walk(target_dir):
                                        for name in files:
                                            candidate_path = os.path.join(root, name)
                                            try:
                                                st = os.stat(candidate_path)
                                            except Exception:
                                                continue
                                            if df.file_size and st.st_size != df.file_size:
                                                continue
                                            # Hash check (sha256)
                                            try:
                                                hasher = hashlib.sha256()
                                                with open(candidate_path, 'rb') as f:
                                                    for chunk in iter(lambda: f.read(1024*1024), b''):
                                                        hasher.update(chunk)
                                                if hasher.hexdigest() == df.content_hash:
                                                    matches.append(candidate_path)
                                                    if len(matches) > 1:
                                                        break
                                            except Exception:
                                                continue
                                        if len(matches) > 1:
                                            break
                                    if len(matches) == 1:
                                        recovered = matches[0]
                                        if not dry_run:
                                            df.datafile = recovered
                                            df.save(update_fields=['datafile'])
                                        updated += 1
                                        hash_recoveries += 1
                                    elif len(matches) > 1:
                                        logger.warning("Reconcile: multiple candidates found for DataFile #%s by hash; skipping ambiguous relink", getattr(df, 'pk', '?'))
                                        ambiguous_matches += 1
                                    else:
                                        recovery_failures += 1
                            except Exception as e:
                                logger.error("Reconcile: hash-recovery failed for DataFile #%s: %s", getattr(df, 'pk', '?'), e)
                                recovery_failures += 1
            except Exception as e:
                logger.error("Reconcile: failed processing DataFile #%s: %s", getattr(df, 'pk', '?'), e)
                recovery_failures += 1

    logger.info("Reconcile complete. updated=%d runs_missing=%d", updated, runs_missing)
    result = {
        'updated': updated,
        'runs_missing': runs_missing,
        'dry_run': dry_run,
        'files_checked': files_checked,
        'already_ok': already_ok,
        'prefix_rewrites': prefix_rewrites,
        'hash_recoveries': hash_recoveries,
        'ambiguous_matches': ambiguous_matches,
        'recovery_failures': recovery_failures,
    }
    _health_set('reconcile_filesystem', result)
    return result


@shared_task(bind=True)
def scan_missing_filesystem(self, dry_run: bool = True, limit: int | None = None):
    """Scan DATA_DIRECTORY for files not yet present in the DB and ingest them.
    - Walk each top-level run directory under DATA_DIRECTORY.
    - For each recognized file extension, add missing DataFile rows and evaluate metadata.
    - Creates ObservationRun when the top-level directory has no matching run.
    """
    base = (
        os.environ.get('DATA_DIRECTORY')
        or os.environ.get('DATA_PATH')
        or '/archive/ftp/'
    )
    # Normalize base
    base = str(base)
    try:
        base = base if base.endswith(os.sep) else (base + os.sep)
    except Exception:
        pass

    added = 0
    checked = 0
    skipped_known = 0
    skipped_unknown_type = 0
    errors = 0
    runs_created = 0
    runs_seen = 0

    try:
        with os.scandir(base) as it:
            for entry in it:
                if not entry.is_dir():
                    continue
                # Skip hidden/system/trash directories at top level
                name = entry.name
                low = name.lower()
                if name.startswith('.') or low.startswith('trash') or name in ('lost+found',):
                    continue
                runs_seen += 1
                run_name = entry.name
                run_dir = os.path.join(base, run_name)
                # Ensure ObservationRun exists
                try:
                    run = ObservationRun.objects.get(name=run_name)
                except ObservationRun.DoesNotExist:
                    try:
                        if not dry_run:
                            run = ObservationRun.objects.create(name=run_name, reduction_status='NE')
                        else:
                            run = None
                        runs_created += 1
                    except Exception:
                        run = None
                        errors += 1
                # Walk files under the run directory
                for root, dirs, files in os.walk(run_dir):
                    for fname in files:
                        try:
                            abs_path = os.path.join(root, fname)
                            checked += 1
                            # Skip if already tracked
                            if DataFile.objects.filter(datafile=abs_path).exists():
                                skipped_known += 1
                                continue
                            # Dry-run: estimate whether the file would be accepted by add_new_data_file
                            if dry_run:
                                suffix = Path(abs_path).suffix
                                # Accepted suffixes as per utilities.add_new_data_file mapping
                                ok = suffix in ['.fit', '.fits', '.FIT', '.FITS',
                                                '.CR2', '.cr2',
                                                '.JPG', '.jpg', '.jpeg', '.JPEG',
                                                '.tiff', '.tif', '.TIF', '.TIFF',
                                                '.ser', '.SER',
                                                '.avi', '.AVI',
                                                '.mov', '.MOV']
                                if ok:
                                    added += 1
                                else:
                                    skipped_unknown_type += 1
                                # Respect limit in dry-run as well
                                if limit and added >= limit:
                                    result = {
                                        'dry_run': True,
                                        'added': added,
                                        'checked': checked,
                                        'skipped_known': skipped_known,
                                        'skipped_unknown_type': skipped_unknown_type,
                                        'errors': errors,
                                        'runs_seen': runs_seen,
                                        'runs_created': runs_created,
                                    }
                                    _health_set('scan_missing_filesystem', result)
                                    return result
                                continue
                            # Real ingestion
                            if run is None:
                                # If creating the run failed in non-dry mode, skip file
                                skipped_unknown_type += 1
                                continue
                            ok = add_new_data_file(Path(abs_path), run, print_to_terminal=False)
                            if ok:
                                added += 1
                                if limit and added >= limit:
                                    result = {
                                        'dry_run': False,
                                        'added': added,
                                        'checked': checked,
                                        'skipped_known': skipped_known,
                                        'skipped_unknown_type': skipped_unknown_type,
                                        'errors': errors,
                                        'runs_seen': runs_seen,
                                        'runs_created': runs_created,
                                    }
                                    _health_set('scan_missing_filesystem', result)
                                    return result
                            else:
                                skipped_unknown_type += 1
                        except Exception:
                            errors += 1
                            continue
    except Exception as e:
        _health_error('scan_missing_filesystem', e)
        return {
            'dry_run': bool(dry_run),
            'added': added,
            'checked': checked,
            'skipped_known': skipped_known,
            'skipped_unknown_type': skipped_unknown_type,
            'errors': errors + 1,
            'runs_seen': runs_seen,
            'runs_created': runs_created,
        }

    result = {
        'dry_run': bool(dry_run),
        'added': added,
        'checked': checked,
        'skipped_known': skipped_known,
        'skipped_unknown_type': skipped_unknown_type,
        'errors': errors,
        'runs_seen': runs_seen,
        'runs_created': runs_created,
    }
    _health_set('scan_missing_filesystem', result)
    return result





@shared_task(bind=True)
def cleanup_expired_downloads(self):
    """Delete ZIP files for expired DownloadJobs and mark them as expired.

    A job is eligible when `expires_at` is set and is in the past.
    The task removes the file at `file_path` (if it exists), clears `file_path`,
    and sets `status='expired'` when not already set.
    """
    now = timezone.now()
    qs = DownloadJob.objects.filter(expires_at__isnull=False, expires_at__lte=now)
    cleaned = 0
    checked = qs.count()
    freed_bytes = 0
    for job in qs.only('pk', 'file_path', 'status'):
        try:
            if job.file_path:
                p = Path(job.file_path)
                try:
                    if p.exists():
                        try:
                            freed_bytes += p.stat().st_size
                        except Exception:
                            pass
                        p.unlink()
                except Exception as e:
                    logger.warning("Cleanup: failed to delete %s for job #%s: %s", job.file_path, job.pk, e)
            job.file_path = ''
            if job.status != 'expired':
                job.status = 'expired'
            job.save(update_fields=['file_path', 'status'])
            cleaned += 1
        except Exception as e:
            logger.error("Cleanup: error processing job #%s: %s", getattr(job, 'pk', '?'), e)

    logger.info("Cleanup expired downloads complete. cleaned=%d", cleaned)
    result = {'cleaned': cleaned, 'checked': checked, 'freed_bytes': int(freed_bytes)}
    _health_set('cleanup_expired_downloads', result)
    return result


@shared_task(bind=True)
def cleanup_orphans_and_hashcheck(self, dry_run: bool = True, fix_missing_hashes: bool = True, limit: int | None = None):
    """Scan DataFiles for orphans/missing files and hash drift.
    - Orphans: DataFile with missing observation_run or file path does not exist → delete (when not dry_run).
    - Hash check: for existing files, compute sha256 and compare to stored content_hash.
      - If missing content_hash and fix_missing_hashes=True, fill it.
      - If drift detected (hash differs), report but do not overwrite.
    """
    from hashlib import sha256
    files_checked = 0
    orphans_deleted = 0
    orphans_count = 0
    files_missing = 0
    missing_deleted = 0
    hash_checked = 0
    hash_set = 0
    hash_drift = 0
    sizes_updated = 0

    qs = DataFile.objects.all().only('pk', 'datafile', 'content_hash', 'file_size', 'observation_run_id')
    if limit and isinstance(limit, int) and limit > 0:
        qs = qs[:limit]
    for df in qs:
        try:
            files_checked += 1
            # Orphan by missing run
            if not df.observation_run_id:
                orphans_count += 1
                if not dry_run:
                    try:
                        df.delete()
                        orphans_deleted += 1
                    except Exception:
                        pass
                continue
            p = Path(df.datafile)
            if not p.exists() or not p.is_file():
                files_missing += 1
                if not dry_run:
                    try:
                        df.delete()
                        missing_deleted += 1
                    except Exception:
                        pass
                continue
            # Existing file: update size, check hash
            try:
                size = p.stat().st_size
                if size != df.file_size:
                    df.file_size = size
                    if not dry_run:
                        try:
                            df.save(update_fields=['file_size'])
                        except Exception:
                            pass
                    sizes_updated += 1
            except Exception:
                pass
            # Hash check (limited by time/size)
            try:
                hasher = sha256()
                with p.open('rb') as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        hasher.update(chunk)
                current_hash = hasher.hexdigest()
                hash_checked += 1
                if not df.content_hash:
                    if fix_missing_hashes and not dry_run:
                        try:
                            df.content_hash = current_hash
                            df.save(update_fields=['content_hash'])
                            hash_set += 1
                        except Exception:
                            pass
                    else:
                        hash_set += 0  # noop
                else:
                    if str(df.content_hash) != current_hash:
                        hash_drift += 1
            except Exception:
                # skip hash errors but continue
                pass
        except Exception as e:
            # continue with next item
            continue

    result = {
        'dry_run': bool(dry_run),
        'files_checked': files_checked,
        'orphans_count': orphans_count,
        'orphans_deleted': orphans_deleted,
        'files_missing': files_missing,
        'missing_deleted': missing_deleted,
        'hash_checked': hash_checked,
        'hash_set': hash_set,
        'hash_drift': hash_drift,
        'sizes_updated': sizes_updated,
    }
    _health_set('cleanup_orphans_hashcheck', result)
    return result
