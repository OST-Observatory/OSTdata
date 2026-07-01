"""Distributed SIMBAD query rate limiting (shared across Celery workers)."""
from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_LOCAL_LOCK = threading.Lock()
_LOCAL_LAST_QUERY_TS = 0.0
_REDIS_KEY = 'ostdata:simbad:last_query_ts'
_REDIS_LOCK_KEY = 'ostdata:simbad:query_lock'


def _min_interval_seconds() -> float:
    return float(getattr(settings, 'AUX_OBJECTS_SIMBAD_MIN_INTERVAL_SECONDS', 10.0))


def _get_redis_client():
    try:
        from adminops.redis_helpers import get_redis_from_broker
        return get_redis_from_broker()
    except Exception:
        return None


def _local_wait(interval: float) -> None:
    global _LOCAL_LAST_QUERY_TS
    with _LOCAL_LOCK:
        now = time.time()
        wait = interval - (now - _LOCAL_LAST_QUERY_TS)
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _LOCAL_LAST_QUERY_TS = now


def wait_for_aux_simbad_query_slot() -> None:
    """
    Block until at least AUX_OBJECTS_SIMBAD_MIN_INTERVAL_SECONDS have elapsed
    since the last SIMBAD query (cluster lookup) across all workers.
    """
    interval = _min_interval_seconds()
    client = _get_redis_client()
    if client is None:
        _local_wait(interval)
        return

    try:
        lock = client.lock(_REDIS_LOCK_KEY, timeout=120, blocking_timeout=120)
        if not lock.acquire(blocking=True):
            logger.warning('SIMBAD rate limit lock timeout; proceeding with local wait')
            _local_wait(interval)
            return
        try:
            while True:
                now = time.time()
                last_raw = client.get(_REDIS_KEY)
                last = float(last_raw) if last_raw else 0.0
                wait = interval - (now - last)
                if wait <= 0:
                    client.set(_REDIS_KEY, str(now))
                    return
                time.sleep(min(wait, 1.0))
        finally:
            lock.release()
    except Exception as exc:
        logger.warning('Redis SIMBAD rate limit failed (%s); using local fallback', exc)
        _local_wait(interval)
