"""
File integrity check of data files: truncated or unreadable files (errors) and non-compliant headers
(warnings). Results are stored in DataFile.file_issues and listed on the admin maintenance page.
"""
from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

from django.utils import timezone

logger = logging.getLogger(__name__)

ERROR = 'error'
WARNING = 'warning'

FITS_SUFFIXES = ('.fits', '.fit', '.fts')
SER_SUFFIXES = ('.ser',)
VIDEO_SUFFIXES = ('.avi', '.mov')

#   astropy messages that mean the data cannot be read completely
_FITS_ERROR_MARKERS = ('truncated', 'missing', 'corrupt', 'empty or corrupt')


def _issue(level, message):
    return {'level': level, 'message': str(message).strip()[:500]}


def _file_kind(datafile):
    file_type = (datafile.file_type or '').upper()
    suffix = Path(str(datafile.datafile)).suffix.lower()
    if file_type == 'FITS' or suffix in FITS_SUFFIXES:
        return 'fits'
    if file_type == 'SER' or suffix in SER_SUFFIXES:
        return 'ser'
    if file_type in ('AVI', 'MOV') or suffix in VIDEO_SUFFIXES:
        return 'video'
    return 'other'


def _check_fits(path):
    from astropy.io import fits

    issues = []
    data_end = None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            with fits.open(path, memmap=False, lazy_load_hdus=False, ignore_missing_simple=True) as hdul:
                # Header problems (e.g. unparsable cards) without changing the file
                hdul.verify('warn')
                # End of the last data byte (without the padding to 2880-byte blocks)
                data_end = max((hdu._data_offset + hdu.size for hdu in hdul
                                if getattr(hdu, '_data_offset', None) is not None), default=None)
        except Exception as exc:
            issues.append(_issue(ERROR, f'FITS file cannot be read: {exc}'))
    file_size = os.path.getsize(path)
    truncation_reported = False
    for warning in caught:
        message = str(warning.message)
        if 'truncated' in message.lower() and data_end is not None:
            # astropy compares with the padded size: also files whose data are complete but whose last
            # block lacks the padding (common, readable by DS9 etc.) are reported as truncated
            if truncation_reported:
                continue
            truncation_reported = True
            if file_size >= data_end:
                issues.append(_issue(WARNING, (
                    'Last FITS block not padded to 2880 bytes (not standard-compliant); '
                    'the image data are complete'
                )))
            else:
                issues.append(_issue(ERROR, (
                    f'FITS file truncated: {data_end - file_size} of {data_end} data bytes missing'
                )))
            continue
        level = ERROR if any(marker in message.lower() for marker in _FITS_ERROR_MARKERS) else WARNING
        issues.append(_issue(level, message))
    return issues


def _check_ser(path):
    from obs_run.ser_parser import SER_HEADER_SIZE, SERParser

    try:
        parser = SERParser(str(path), SER_16bit_shift_correction=False)
    except Exception as exc:
        return [_issue(ERROR, f'SER header cannot be read: {exc}')]
    try:
        issues = []
        if parser.warn_message:
            issues.append(_issue(WARNING, parser.warn_message))
        if parser.frame_count <= 0 or parser.frame_size <= 0:
            issues.append(_issue(ERROR, 'SER file contains no frames'))
        else:
            expected = SER_HEADER_SIZE + parser.frame_count * parser.frame_size
            actual = os.path.getsize(path)
            if actual < expected:
                complete = max(0, (actual - SER_HEADER_SIZE) // parser.frame_size)
                issues.append(_issue(
                    ERROR,
                    f'SER file truncated: {actual} of {expected} bytes '
                    f'({complete} of {parser.frame_count} frames complete)',
                ))
        return issues
    finally:
        parser.release()


def _check_video(path):
    try:
        import cv2
    except Exception:
        return []
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return [_issue(ERROR, 'Video file cannot be opened')]
        ok, _frame = cap.read()
        if not ok:
            return [_issue(ERROR, 'Video file contains no readable frame')]
        return []
    finally:
        cap.release()


def check_path(path, kind):
    """
    Issues of one existing file (no database access). Runs inside the isolated checker process:
    the readers use native code (astropy, OpenCV/FFmpeg) that can crash on broken files.
    """
    path = Path(path)
    try:
        if kind == 'fits':
            issues = _check_fits(path)
        elif kind == 'ser':
            issues = _check_ser(path)
        elif kind == 'video':
            issues = _check_video(path)
        else:
            issues = []
    except Exception as exc:
        logger.warning('File check failed for %s', path, exc_info=True)
        issues = [_issue(ERROR, f'File check failed: {exc}')]
    # Same message reported twice (e.g. by astropy and a logger) counts once
    unique = []
    for issue in issues:
        if issue not in unique:
            unique.append(issue)
    return unique


def _ffprobe_video(path):
    """(codec, width, height) via ffprobe, None if ffprobe is missing; raises if it cannot read the file."""
    import json
    import shutil
    import subprocess

    ffprobe = shutil.which('ffprobe')
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height',
         '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=120,
    )
    streams = json.loads(result.stdout or '{}').get('streams') or []
    if result.returncode != 0 or not streams:
        raise ValueError((result.stderr or 'no video stream').strip()[:200])
    stream = streams[0]
    return stream.get('codec_name') or '?', stream.get('width'), stream.get('height')


def reader_failure_issues(path, kind, reason):
    """
    Issues when the reader process crashed or hung. For videos this is often OpenCV's bundled FFmpeg
    failing on a codec/container players handle fine: ask ffprobe (if installed) before calling the
    file broken.
    """
    if kind != 'video':
        return [_issue(ERROR, f'File reader {reason}: the file is probably corrupt')]
    try:
        probe = _ffprobe_video(path)
    except Exception as exc:
        return [_issue(ERROR, f'Video cannot be read: OpenCV {reason}, ffprobe: {exc}')]
    if probe is None:
        return [_issue(WARNING, (
            f'Video could not be read by the archive (OpenCV {reason}); it may still play in other software '
            '(install ffprobe on the server for a second check)'
        ))]
    codec, width, height = probe
    return [_issue(WARNING, (
        f'Video readable by ffprobe ({codec}, {width}x{height}), but not by OpenCV ({reason}): '
        'no preview in the archive'
    ))]


class WorkerFailure(Exception):
    """The isolated child process crashed or did not answer in time (reason in .reason)."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class IsolatedWorker:
    """
    Runs requests (one JSON line each) in a long-lived child process (obs_run/file_check_worker.py).
    Native readers (astropy, OpenCV/FFmpeg) can crash on broken or unusual files (e.g. glibc
    'corrupted double-linked list'); then only the child dies, the request raises WorkerFailure and the
    next request starts a fresh process, instead of the crash killing the caller (check command, Celery
    worker, Gunicorn worker, directory watchdog). subprocess instead of multiprocessing: Celery workers
    are daemonic and may not start multiprocessing children.
    """

    def __init__(self, timeout=300, command=None):
        self.timeout = timeout
        self.command = command  # tests: replace the worker
        self.proc = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _start(self):
        import subprocess
        import sys

        from django.conf import settings

        self.proc = subprocess.Popen(
            self.command or [sys.executable, '-m', 'obs_run.file_check_worker'],
            cwd=str(settings.BASE_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # reader warnings/crash output
            text=True,
        )

    def _kill(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=10)
            except Exception:
                pass
            self.proc = None

    def request(self, payload):
        import json
        import select

        if self.proc is None or self.proc.poll() is not None:
            self._start()
        try:
            self.proc.stdin.write(json.dumps(payload) + '\n')
            self.proc.stdin.flush()
            ready, _, _ = select.select([self.proc.stdout], [], [], self.timeout)
            line = self.proc.stdout.readline() if ready else ''
        except (BrokenPipeError, OSError):
            line = ''
        if line:
            return json.loads(line)
        if self.proc.poll() is None:
            reason = f'did not finish within {self.timeout} s'
        else:
            reason = f'crashed (exit code {self.proc.returncode})'
        logger.warning('Isolated %s request %s: %s', payload.get('action'), reason, payload.get('path'))
        self._kill()
        raise WorkerFailure(reason)

    def close(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=10)
            except Exception:
                pass
        self._kill()


class IsolatedChecker(IsolatedWorker):
    """File integrity checks (check_path) in the isolated child process."""

    def check(self, path, kind):
        try:
            return self.request({'action': 'check', 'path': str(path), 'kind': kind})
        except WorkerFailure as failure:
            return reader_failure_issues(path, kind, failure.reason)


def check_datafile(datafile, checker=None):
    """List of issues of one data file (empty if the file is fine)."""
    path = Path(str(datafile.datafile))
    if not path.is_file():
        return [_issue(ERROR, 'File missing on disk')]
    kind = _file_kind(datafile)
    if kind == 'other':
        return []
    if checker is not None:
        return checker.check(path, kind)
    with IsolatedChecker() as own_checker:
        return own_checker.check(path, kind)


def update_file_issues(datafile, checker=None):
    """Check the file and store the result (plain update: no history entry for a diagnostic field)."""
    from obs_run.models import DataFile

    issues = check_datafile(datafile, checker)
    level = issue_level(issues)
    checked_at = timezone.now()
    DataFile.objects.filter(pk=datafile.pk).update(
        file_issues=issues, file_issue_level=level, file_issues_checked_at=checked_at,
    )
    datafile.file_issues = issues
    datafile.file_issue_level = level
    datafile.file_issues_checked_at = checked_at
    return issues


def issue_level(issues):
    """Highest level of a list of issues: 'error', 'warning' or ''."""
    levels = {issue.get('level') for issue in issues}
    if ERROR in levels:
        return ERROR
    return WARNING if WARNING in levels else ''


def check_data_files(only_unchecked=False, limit=None, kinds=None, progress=None, only_issues=False):
    """
    Check many data files; returns a summary. kinds: subset of ('fits', 'ser', 'video', 'other').
    only_issues: re-check only files whose last check found errors or warnings.
    progress: optional callable(checked) called every 500 files.
    """
    from obs_run.models import DataFile

    queryset = DataFile.objects.order_by('pk').only('pk', 'datafile', 'file_type')
    if only_unchecked:
        queryset = queryset.filter(file_issues_checked_at__isnull=True)
    if only_issues:
        queryset = queryset.exclude(file_issue_level='')
    summary = {'checked': 0, 'with_errors': 0, 'with_warnings': 0, 'only_unchecked': bool(only_unchecked),
               'only_issues': bool(only_issues)}
    with IsolatedChecker() as checker:
        for datafile in queryset.iterator(chunk_size=500):
            if kinds and _file_kind(datafile) not in kinds:
                continue
            if limit and summary['checked'] >= limit:
                break
            level = issue_level(update_file_issues(datafile, checker))
            summary['checked'] += 1
            if level == ERROR:
                summary['with_errors'] += 1
            elif level == WARNING:
                summary['with_warnings'] += 1
            if progress and summary['checked'] % 500 == 0:
                progress(summary['checked'])
    return summary
