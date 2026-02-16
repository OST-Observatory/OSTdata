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
from obs_run.utils import should_allow_auto_update
from utilities import (
    add_new_data_file, get_effective_exposure_type_filter, annotate_effective_exposure_type,
    evaluate_data_file, update_observation_run_photometry_spectroscopy, update_object_photometry_spectroscopy,
)
from obs_run.plate_solving import PlateSolvingService, solve_and_update_datafile

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
            # Use effective exposure type for filtering
            qs = annotate_effective_exposure_type(qs)
            qs = qs.filter(effective_exposure_type__in=f['exposure_type'])
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
        if f.get('obs_date_contains'):
            qs = qs.filter(obs_date__icontains=f['obs_date_contains'])
        if f.get('plate_solved') is not None:
            qs = qs.filter(plate_solved=bool(f['plate_solved']))

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
                # After scanning this run directory, recompute mid_observation_jd
                # Only if override flag is not set
                try:
                    if not dry_run and run is not None:
                        if should_allow_auto_update(run, 'mid_observation_jd'):
                            qs = DataFile.objects.filter(observation_run=run, hjd__gt=2451545)
                            a = qs.order_by('hjd').values_list('hjd', flat=True).first()
                            b = qs.order_by('-hjd').values_list('hjd', flat=True).first()
                            if a is None and b is None:
                                run.mid_observation_jd = 0.0
                            elif a is None or b is None:
                                run.mid_observation_jd = float(a or b or 0.0)
                            else:
                                run.mid_observation_jd = float(a + (b - a) / 2.0)
                            run.save(update_fields=['mid_observation_jd'])
                except Exception:
                    # Do not fail the whole task on recompute errors
                    errors += 1
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
def cleanup_orphan_objects(self, dry_run: bool = True):
    """Clean up Objects that have no associated DataFiles.
    
    After files are deleted, Objects may become "orphaned" with no
    remaining DataFile associations. This task finds and removes them.
    Also recalculates first_hjd for Objects that still have DataFiles.
    """
    from django.db.models import Count
    from objects.models import Object
    
    objects_checked = 0
    orphans_found = 0
    orphans_deleted = 0
    first_hjd_updated = 0
    observation_run_cleaned = 0
    
    # Find Objects with zero DataFiles (exclude API-created placeholders until DataFiles linked)
    orphans = Object.objects.annotate(df_count=Count('datafiles')).filter(
        df_count=0, exclude_from_orphan_cleanup=False
    )
    orphans_found = orphans.count()
    
    if not dry_run:
        # Delete orphan Objects
        for obj in orphans:
            try:
                # Also clean up the M2M relation to observation_run before deleting
                obj.observation_run.clear()
                obj.delete()
                orphans_deleted += 1
            except Exception as e:
                logger.warning("Failed to delete orphan Object #%s: %s", obj.pk, e)
    
    # For remaining Objects, recalculate first_hjd based on current DataFiles
    remaining = Object.objects.annotate(df_count=Count('datafiles')).filter(df_count__gt=0)
    objects_checked = remaining.count()
    
    for obj in remaining:
        try:
            # Get the earliest HJD from associated DataFiles
            valid_files = obj.datafiles.filter(hjd__gt=2451545).order_by('hjd')
            if valid_files.exists():
                new_first_hjd = valid_files.first().hjd
            else:
                new_first_hjd = 0.0
            
            if obj.first_hjd != new_first_hjd:
                if not dry_run:
                    obj.first_hjd = new_first_hjd
                    obj.save(update_fields=['first_hjd'])
                first_hjd_updated += 1
            
            # Also clean up observation_run M2M if no DataFiles remain for that run
            for run in list(obj.observation_run.all()):
                has_files_in_run = obj.datafiles.filter(observation_run=run).exists()
                if not has_files_in_run:
                    if not dry_run:
                        obj.observation_run.remove(run)
                    observation_run_cleaned += 1
        except Exception as e:
            logger.warning("Failed to update Object #%s: %s", obj.pk, e)
    
    result = {
        'dry_run': bool(dry_run),
        'objects_checked': objects_checked,
        'orphans_found': orphans_found,
        'orphans_deleted': orphans_deleted,
        'first_hjd_updated': first_hjd_updated,
        'observation_run_cleaned': observation_run_cleaned,
    }
    _health_set('cleanup_orphan_objects', result)
    logger.info("Cleanup orphan objects complete: %s", result)
    return result


@shared_task(bind=True)
def unlink_non_light_datafiles_from_objects(self, dry_run: bool = True):
    """Remove Object–DataFile associations for all DataFiles that are not Light frames.
    
    Non-Light frames (flats, darks, bias, etc.) are unlinked from their Objects.
    Affected objects and observation runs get photometry/spectroscopy flags updated.
    """
    from objects.models import Object
    
    # Through table for Object <-> DataFile M2M
    through = Object.datafiles.through
    linked_df_ids = through.objects.values_list('datafile_id', flat=True).distinct()
    
    qs = annotate_effective_exposure_type(DataFile.objects.filter(pk__in=linked_df_ids))
    non_light = qs.exclude(effective_exposure_type='LI')
    files_found = non_light.count()
    unlinks_done = 0
    objects_updated = set()
    runs_updated = set()
    
    if not dry_run:
        for datafile in non_light.only('pk').iterator():
            try:
                objects = list(datafile.object_set.only('pk').all())
                for obj in objects:
                    obj.datafiles.remove(datafile)
                    unlinks_done += 1
                    objects_updated.add(obj.pk)
                for obj in objects:
                    try:
                        update_object_photometry_spectroscopy(obj)
                    except Exception as e:
                        logger.warning("photometry/spectroscopy update failed for Object #%s: %s", obj.pk, e)
                for obj in objects:
                    for run in obj.observation_run.only('pk'):
                        try:
                            update_observation_run_photometry_spectroscopy(run)
                            runs_updated.add(run.pk)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning("Failed to unlink DataFile #%s: %s", datafile.pk, e)
    
    result = {
        'dry_run': bool(dry_run),
        'files_found': files_found,
        'unlinks_done': unlinks_done,
        'objects_updated': len(objects_updated),
        'runs_updated': len(runs_updated),
    }
    _health_set('unlink_non_light_datafiles', result)
    logger.info("Unlink non-Light DataFiles from Objects complete: %s", result)
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


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def refresh_dashboard_stats(self):
    """
    Background task to pre-compute and cache dashboard statistics.
    
    This task uses aggregation queries for efficiency and caches the results.
    Can be scheduled via Celery Beat (e.g., every 15-30 minutes) or triggered manually.
    
    Cache keys:
    - dashboard_stats_v2: Main stats (30 min TTL)
    - dashboard_storage_size: Storage size (2 hour TTL)
    """
    from django.core.cache import cache
    from django.db.models import Count, Q
    from datetime import datetime, timedelta
    from django.utils.timezone import make_aware
    from objects.models import Object
    import environ
    from obs_run.auxil import get_size_dir
    
    try:
        dtime_naive = datetime.now() - timedelta(days=7)
        aware_datetime = make_aware(dtime_naive)
        
        # === FILES: Single aggregated query ===
        # Annotate with effective_exposure_type for spectra counting
        datafiles_annotated = annotate_effective_exposure_type(DataFile.objects.all())
        file_stats = datafiles_annotated.aggregate(
            total=Count('pk'),
            bias=Count('pk', filter=get_effective_exposure_type_filter('BI', '')),
            darks=Count('pk', filter=get_effective_exposure_type_filter('DA', '')),
            flats=Count('pk', filter=get_effective_exposure_type_filter('FL', '')),
            lights=Count('pk', filter=get_effective_exposure_type_filter('LI', '')),
            waves=Count('pk', filter=get_effective_exposure_type_filter('WA', '')),
            # Spectra: Light frames with spectrograph != 'N' (NONE)
            spectra=Count('pk', filter=Q(effective_exposure_type='LI') & ~Q(spectrograph='N')),
            fits=Count('pk', filter=Q(file_type='FITS')),
            jpeg=Count('pk', filter=Q(file_type='JPG')),
            cr2=Count('pk', filter=Q(file_type='CR2')),
            tiff=Count('pk', filter=Q(file_type='TIFF')),
            ser=Count('pk', filter=Q(file_type='SER')),
        )
        files_7d_count = DataFile.history.filter(history_date__gte=aware_datetime).count()
        
        # === OBJECTS: Single aggregated query ===
        object_stats = Object.objects.aggregate(
            total=Count('pk'),
            galaxies=Count('pk', filter=Q(object_type='GA')),
            star_clusters=Count('pk', filter=Q(object_type='SC')),
            nebulae=Count('pk', filter=Q(object_type='NE')),
            stars=Count('pk', filter=Q(object_type='ST')),
            solar_system=Count('pk', filter=Q(object_type='SO')),
            other=Count('pk', filter=Q(object_type='OT')),
            unknown=Count('pk', filter=Q(object_type='UK')),
        )
        objects_7d_count = Object.history.filter(history_date__gte=aware_datetime).count()
        
        # === RUNS: Single aggregated query ===
        run_stats = ObservationRun.objects.aggregate(
            total=Count('pk'),
            partly_reduced=Count('pk', filter=Q(reduction_status='PR')),
            fully_reduced=Count('pk', filter=Q(reduction_status='FR')),
            reduction_error=Count('pk', filter=Q(reduction_status='ER')),
            not_reduced=Count('pk', filter=Q(reduction_status='NE')),
        )
        runs_7d_count = ObservationRun.history.filter(history_date__gte=aware_datetime).count()
        
        # === STORAGE SIZE ===
        env = environ.Env()
        environ.Env.read_env()
        data_path = env("DATA_DIRECTORY", default='/archive/ftp/')
        try:
            storage_size = get_size_dir(data_path) * pow(1000, -4)
        except Exception:
            storage_size = 0
        
        # Build stats dict
        stats = {
            'files': {
                'total': file_stats['total'] or 0,
                'total_last_week': files_7d_count,
                'bias': file_stats['bias'] or 0,
                'darks': file_stats['darks'] or 0,
                'flats': file_stats['flats'] or 0,
                'lights': file_stats['lights'] or 0,
                'waves': file_stats['waves'] or 0,
                'spectra': file_stats['spectra'] or 0,
                'fits': file_stats['fits'] or 0,
                'jpeg': file_stats['jpeg'] or 0,
                'cr2': file_stats['cr2'] or 0,
                'tiff': file_stats['tiff'] or 0,
                'ser': file_stats['ser'] or 0,
                'storage_size': storage_size,
            },
            'objects': {
                'total': object_stats['total'] or 0,
                'total_last_week': objects_7d_count,
                'galaxies': object_stats['galaxies'] or 0,
                'star_clusters': object_stats['star_clusters'] or 0,
                'nebulae': object_stats['nebulae'] or 0,
                'stars': object_stats['stars'] or 0,
                'solar_system': object_stats['solar_system'] or 0,
                'other': object_stats['other'] or 0,
                'unknown': object_stats['unknown'] or 0,
            },
            'runs': {
                'total': run_stats['total'] or 0,
                'total_last_week': runs_7d_count,
                'partly_reduced': run_stats['partly_reduced'] or 0,
                'fully_reduced': run_stats['fully_reduced'] or 0,
                'reduction_error': run_stats['reduction_error'] or 0,
                'not_reduced': run_stats['not_reduced'] or 0,
            }
        }
        
        # Cache results
        cache.set('dashboard_stats_v2', stats, timeout=1800)  # 30 min
        cache.set('dashboard_storage_size', storage_size, timeout=7200)  # 2 hours
        
        result = {
            'files_total': stats['files']['total'],
            'objects_total': stats['objects']['total'],
            'runs_total': stats['runs']['total'],
            'storage_size_tb': storage_size,
        }
        _health_set('refresh_dashboard_stats', result)
        logger.info("Dashboard stats refreshed: %s files, %s objects, %s runs", 
                    stats['files']['total'], stats['objects']['total'], stats['runs']['total'])
        return result
        
    except Exception as e:
        _health_error('refresh_dashboard_stats', e)
        logger.error("Failed to refresh dashboard stats: %s", e)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def plate_solve_pending_files(self):
    """
    Background task to plate solve pending Light frames.
    
    Processes files where:
    - effective_exposure_type == 'LI' (Light frames)
    - plate_solved == False OR plate_solve_attempted_at is None
    - wcs_override == False (don't overwrite manual values)
    - spectrograph == 'N' (exclude spectra)
    - spectroscopy == False (exclude files marked as spectroscopy)
    
    Processes up to PLATE_SOLVING_BATCH_SIZE files per run (default: 10).
    """
    from django.db.models import Q, Case, When, Value, F
    from django.db.models import CharField
    from pathlib import Path
    
    try:
        from adminops.redis_helpers import plate_solving_task_enabled_get
        redis_enabled = plate_solving_task_enabled_get()
        # Redis override takes precedence; if not set, use settings
        enabled = redis_enabled if redis_enabled is not None else getattr(settings, 'PLATE_SOLVING_ENABLED', False)
        if not enabled:
            logger.info("Plate solving task is disabled, skipping")
            return {'skipped': True, 'reason': 'disabled'}
        
        batch_size = getattr(settings, 'PLATE_SOLVING_BATCH_SIZE', 10)
        
        # Query for Light frames that need plate solving
        # Exclude spectra: spectrograph != 'N' OR spectroscopy=True
        queryset = DataFile.objects.filter(
            Q(plate_solved=False) | Q(plate_solve_attempted_at__isnull=True),
            wcs_override=False,
            spectrograph='N',  # Exclude spectra (only process files without spectrograph)
            spectroscopy=False  # Exclude files marked as spectroscopy
        )
        
        # Annotate with effective_exposure_type and filter for Light frames
        # Use a different annotation name to avoid conflict with the property
        queryset = queryset.annotate(
            annotated_effective_exposure_type=Case(
                # Priority 1: User-set type
                When(
                    Q(exposure_type_user__isnull=False) & ~Q(exposure_type_user=''),
                    then='exposure_type_user'
                ),
                # Priority 2: ML type matches header type
                When(
                    Q(exposure_type_ml__isnull=False) & 
                    ~Q(exposure_type_ml='') & 
                    Q(exposure_type_ml=F('exposure_type')),
                    then='exposure_type_ml'
                ),
                # Priority 3: ML type doesn't match header type -> Unknown
                When(
                    Q(exposure_type_ml__isnull=False) & ~Q(exposure_type_ml=''),
                    then=Value('UK')
                ),
                # Priority 4: Header-based type
                default='exposure_type',
                output_field=CharField(max_length=2)
            )
        )
        queryset = queryset.filter(annotated_effective_exposure_type='LI')
        
        # Limit to batch size
        files_to_process = list(queryset[:batch_size])
        
        if not files_to_process:
            result = {'processed': 0, 'succeeded': 0, 'failed': 0}
            _health_set('plate_solve_pending_files', result)
            return result
        
        logger.info(f"Plate solving {len(files_to_process)} files")
        
        service = PlateSolvingService()
        succeeded = 0
        failed = 0
        
        for datafile in files_to_process:
            result = solve_and_update_datafile(datafile, service=service, save=True)
            if result['success']:
                succeeded += 1
                logger.info(f"Successfully plate solved file {datafile.pk}: {Path(datafile.datafile).name}")
            else:
                failed += 1
        
        result = {
            'processed': len(files_to_process),
            'succeeded': succeeded,
            'failed': failed
        }
        _health_set('plate_solve_pending_files', result)
        logger.info(f"Plate solving batch complete: {succeeded} succeeded, {failed} failed")
        return result
        
    except Exception as e:
        _health_error('plate_solve_pending_files', e)
        logger.error("Failed to plate solve pending files: %s", e)
        raise self.retry(exc=e)


@shared_task(bind=True)
def re_evaluate_plate_solved_files(self):
    """
    Re-run evaluate_data_file for plate-solved files when:
    1. No header coordinates were present (ra==-1 or dec==-1), or
    2. WCS center coordinates differ from header (ra,dec) by more than threshold.

    Only processes files with re_evaluated_after_plate_solve=False (avoids double evaluation,
    independent of Redis persistence).
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from django.db.models import Q, F, Case, When, Value, CharField

    try:
        from adminops.redis_helpers import plate_solving_task_enabled_get
        redis_enabled = plate_solving_task_enabled_get()
        enabled = redis_enabled if redis_enabled is not None else getattr(settings, 'PLATE_SOLVING_ENABLED', False)
        if not enabled:
            logger.info("Plate solving task is disabled, skipping re-evaluation")
            return {'skipped': True, 'reason': 'disabled'}
    except Exception:
        enabled = getattr(settings, 'PLATE_SOLVING_ENABLED', False)
        if not enabled:
            return {'skipped': True, 'reason': 'disabled'}

    threshold_arcmin = getattr(settings, 'PLATE_SOLVING_RE_EVAL_COORD_THRESHOLD_ARCMIN', 5.0)
    batch_size = getattr(settings, 'PLATE_SOLVING_RE_EVAL_BATCH_SIZE', 50)

    # Only process files not yet re-evaluated (flag-based, avoids double evaluation, Redis-independent)
    queryset = DataFile.objects.filter(
        plate_solved=True,
        re_evaluated_after_plate_solve=False,
        wcs_override=False,
        spectrograph='N',
        spectroscopy=False,
    ).select_related('observation_run')
    queryset = queryset.annotate(
        annotated_effective_exposure_type=Case(
            When(Q(exposure_type_user__isnull=False) & ~Q(exposure_type_user=''), then='exposure_type_user'),
            When(
                Q(exposure_type_ml__isnull=False) & ~Q(exposure_type_ml='') & Q(exposure_type_ml=F('exposure_type')),
                then='exposure_type_ml'
            ),
            When(Q(exposure_type_ml__isnull=False) & ~Q(exposure_type_ml=''), then=Value('UK')),
            default='exposure_type',
            output_field=CharField(max_length=2)
        )
    )
    queryset = queryset.filter(annotated_effective_exposure_type='LI')

    evaluated = 0
    skipped = 0
    errors = 0

    for datafile in queryset[:batch_size]:
        try:
            condition1 = (datafile.ra in (-1, None) or datafile.dec in (-1, None))
            condition2 = False
            if not condition1 and datafile.wcs_ra is not None and datafile.wcs_dec is not None:
                c_header = SkyCoord(ra=datafile.ra * u.deg, dec=datafile.dec * u.deg)
                c_wcs = SkyCoord(ra=datafile.wcs_ra * u.deg, dec=datafile.wcs_dec * u.deg)
                sep_arcmin = c_header.separation(c_wcs).arcmin
                condition2 = sep_arcmin > threshold_arcmin

            if condition1 or condition2:
                if datafile.observation_run and datafile.wcs_ra is not None and datafile.wcs_dec is not None:
                    # Use WCS coordinates for object lookup (header had none or differed significantly)
                    datafile.ra = datafile.wcs_ra
                    datafile.dec = datafile.wcs_dec
                    datafile.save(update_fields=['ra', 'dec'])
                    evaluate_data_file(datafile, datafile.observation_run, skip_if_object_has_overrides=True)
                    update_observation_run_photometry_spectroscopy(datafile.observation_run)
                    for obj in datafile.object_set.all():
                        update_object_photometry_spectroscopy(obj)
                    evaluated += 1
                    logger.debug(f"Re-evaluated plate-solved file {datafile.pk} (cond1={condition1}, cond2={condition2})")
                else:
                    skipped += 1
            else:
                skipped += 1
            # Mark as processed to avoid double evaluation (independent of Redis persistence)
            DataFile.objects.filter(pk=datafile.pk).update(re_evaluated_after_plate_solve=True)
        except Exception as e:
            errors += 1
            logger.warning(f"Re-evaluation failed for datafile {datafile.pk}: {e}")
            # Still mark as processed to avoid retrying failed files indefinitely
            DataFile.objects.filter(pk=datafile.pk).update(re_evaluated_after_plate_solve=True)

    result = {'evaluated': evaluated, 'skipped': skipped, 'errors': errors}
    _health_set('re_evaluate_plate_solved_files', result)
    if evaluated or errors:
        logger.info(f"Re-evaluation of plate-solved files: {result}")
    return result

