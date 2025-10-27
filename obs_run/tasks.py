from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
import hashlib

from celery import shared_task
import os
import logging
from django.utils import timezone

from obs_run.models import DownloadJob, DataFile, ObservationRun

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def build_zip_task(self, job_id: int):
    """Build a ZIP for a DownloadJob and update its progress fields."""
    try:
        job = DownloadJob.objects.get(pk=job_id)
    except DownloadJob.DoesNotExist:
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
            job.save(update_fields=['status', 'error', 'finished_at'])
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
        with zipfile.ZipFile(tmp_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for p, dfpk in paths:
                arcname = f"{dfpk}_{p.name}"
                try:
                    zf.write(p, arcname=arcname)
                    try:
                        done += p.stat().st_size
                    except Exception:
                        pass
                except Exception:
                    continue
                # Update progress occasionally
                if total > 0:
                    prog = int(min(100, max(0, round(done * 100 / total))))
                    DownloadJob.objects.filter(pk=job.pk).update(bytes_done=done, progress=prog)

        job.status = 'done'
        job.progress = 100
        job.bytes_done = done
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'progress', 'bytes_done', 'finished_at'])
    except Exception as e:
        DownloadJob.objects.filter(pk=job.pk).update(status='failed', error=str(e), finished_at=timezone.now())


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
    for run in ObservationRun.objects.all():
        expected_prefix = os.path.join(base, run.name) + os.sep
        if run.name not in dirnames:
            runs_missing += 1
            logger.warning("Reconcile: run directory missing for '%s' under %s", run.name, base)

        # Iterate files for this run
        for df in DataFile.objects.filter(observation_run=run).only('pk', 'datafile', 'content_hash', 'file_size'):
            try:
                p = str(df.datafile)
                # Quick check: if already correct, skip
                if p.startswith(expected_prefix):
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
                                    elif len(matches) > 1:
                                        logger.warning("Reconcile: multiple candidates found for DataFile #%s by hash; skipping ambiguous relink", getattr(df, 'pk', '?'))
                            except Exception as e:
                                logger.error("Reconcile: hash-recovery failed for DataFile #%s: %s", getattr(df, 'pk', '?'), e)
            except Exception as e:
                logger.error("Reconcile: failed processing DataFile #%s: %s", getattr(df, 'pk', '?'), e)

    logger.info("Reconcile complete. updated=%d runs_missing=%d", updated, runs_missing)
    return {'updated': updated, 'runs_missing': runs_missing}




