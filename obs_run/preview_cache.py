"""
Disk cache of rendered previews (SER_THUMBNAIL_CACHE_DIR): sky view JPEGs (obs_run/sky_view.py) and
SER/AVI/MOV thumbnails (obs_run/ser_thumbnails.py). Size status for the admin maintenance page and an
optional cleanup (no automatic size limit). A cache hit updates the file's mtime, so the mtime is the
time of the last use.
"""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# df<pk>_<content hash>_sky<max_dim>[_v<n>].jpg / df<pk>_<content hash>_w<max_dim>.png
_SKY_NAME = re.compile(r'^df(?P<pk>\d+)_(?P<digest>.+)_sky\d+(?P<version>_v\d+)?\.jpg$')
_THUMB_NAME = re.compile(r'^df(?P<pk>\d+)_(?P<digest>.+)_w\d+\.png$')
SKY_IMAGE_VERSION = '_v2'  # see obs_run.sky_view._cache_path
KINDS = ('sky', 'thumbnail', 'other')


def cache_dir() -> Path:
    base = getattr(settings, 'SER_THUMBNAIL_CACHE_DIR', None)
    return Path(base) if base else Path(settings.BASE_DIR) / 'data' / 'ser_thumbnails'


def touch(path) -> None:
    """Mark a cache file as used (cache hit)."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _classify(name):
    """(kind, datafile pk, content hash, outdated format) of a cache file name."""
    match = _SKY_NAME.match(name)
    if match:
        return 'sky', int(match['pk']), match['digest'], match['version'] != SKY_IMAGE_VERSION
    match = _THUMB_NAME.match(name)
    if match:
        return 'thumbnail', int(match['pk']), match['digest'], False
    return 'other', None, None, False


def _entries():
    directory = cache_dir()
    if not directory.is_dir():
        return
    with os.scandir(directory) as it:
        for entry in it:
            if entry.is_file(follow_symlinks=False):
                yield entry, entry.stat(follow_symlinks=False)


def cache_status() -> dict:
    """Number, size and age of the cached previews per kind, and free space of the cache volume."""
    kinds = {kind: {'files': 0, 'bytes': 0, 'oldest_use': None, 'newest_use': None} for kind in KINDS}
    for entry, stat in _entries():
        kind = kinds[_classify(entry.name)[0]]
        kind['files'] += 1
        kind['bytes'] += stat.st_size
        kind['oldest_use'] = min(kind['oldest_use'] or stat.st_mtime, stat.st_mtime)
        kind['newest_use'] = max(kind['newest_use'] or stat.st_mtime, stat.st_mtime)
    directory = cache_dir()
    free_bytes = None
    try:
        st = os.statvfs(directory if directory.is_dir() else directory.parent)
        free_bytes = st.f_frsize * st.f_bavail
    except OSError:
        pass
    return {
        'kinds': kinds,
        'total_files': sum(k['files'] for k in kinds.values()),
        'total_bytes': sum(k['bytes'] for k in kinds.values()),
        'free_bytes': free_bytes,
    }


def cleanup_cache(max_age_days=None, dry_run=False) -> dict:
    """
    Remove previews unused for max_age_days, of deleted or changed files (content hash differs), and
    sky images in an outdated format. Everything is re-rendered on demand.
    """
    from obs_run.models import DataFile

    if max_age_days is None:
        max_age_days = int(getattr(settings, 'PREVIEW_CACHE_MAX_AGE_DAYS', 90))
    cutoff = time.time() - max_age_days * 86400
    candidates = []
    for entry, stat in _entries():
        kind, pk, digest, outdated = _classify(entry.name)
        if kind == 'other':
            continue
        candidates.append((entry.path, stat, kind, pk, digest, outdated))
    current_hash = dict(
        DataFile.objects.filter(pk__in={c[3] for c in candidates}).values_list('pk', 'content_hash')
    )
    summary = {'dry_run': bool(dry_run), 'max_age_days': max_age_days, 'removed_files': 0, 'removed_bytes': 0,
               'reasons': {'unused': 0, 'file_deleted': 0, 'file_changed': 0, 'outdated_format': 0}}
    for path, stat, kind, pk, digest, outdated in candidates:
        if pk not in current_hash:
            reason = 'file_deleted'
        elif digest != ((current_hash[pk] or 'nohash').strip() or 'nohash'):
            reason = 'file_changed'
        elif outdated:
            reason = 'outdated_format'
        elif stat.st_mtime < cutoff:
            reason = 'unused'
        else:
            continue
        if not dry_run:
            try:
                os.remove(path)
            except OSError:
                logger.warning('Could not remove cached preview %s', path, exc_info=True)
                continue
        summary['reasons'][reason] += 1
        summary['removed_files'] += 1
        summary['removed_bytes'] += stat.st_size
    return summary
