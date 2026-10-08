"""Error counter and heartbeat of the data directory watchdog, stored in Redis.

The watchdog runs as a separate process (``manage.py watch_data``). It installs
``RedisErrorHandler`` on the root logger, so every ERROR log record emitted in
that process is counted. The admin health page reads the status via
``watchdog_status_get``.
"""
import json
import logging

from django.utils import timezone

from adminops.redis_helpers import get_redis_from_broker

_STATUS_KEY = 'ostdata:watchdog:status'
_ERRORS_KEY = 'ostdata:watchdog:errors'
_MAX_RECENT_ERRORS = 50
_MAX_MESSAGE_LENGTH = 2000


def watchdog_mark_started():
    """Record watcher start time and initial heartbeat."""
    client = get_redis_from_broker()
    if not client:
        return
    try:
        now = timezone.now().isoformat()
        client.hset(_STATUS_KEY, mapping={'started_at': now, 'last_heartbeat': now})
    except Exception:
        pass


def watchdog_heartbeat():
    """Update the 'watcher is alive' timestamp."""
    client = get_redis_from_broker()
    if not client:
        return
    try:
        client.hset(_STATUS_KEY, 'last_heartbeat', timezone.now().isoformat())
    except Exception:
        pass


def watchdog_record_error(message: str, logger_name: str = ''):
    """Increment the error counter and keep the message in a capped list."""
    client = get_redis_from_broker()
    if not client:
        return
    try:
        now = timezone.now().isoformat()
        message = (message or '')[:_MAX_MESSAGE_LENGTH]
        entry = json.dumps({'ts': now, 'logger': logger_name, 'message': message})
        pipe = client.pipeline()
        pipe.hincrby(_STATUS_KEY, 'error_count', 1)
        pipe.hset(_STATUS_KEY, mapping={'last_error': message, 'last_error_at': now})
        pipe.lpush(_ERRORS_KEY, entry)
        pipe.ltrim(_ERRORS_KEY, 0, _MAX_RECENT_ERRORS - 1)
        pipe.execute()
    except Exception:
        pass


def watchdog_errors_reset():
    """Reset error counter and recent errors (heartbeat info is kept)."""
    client = get_redis_from_broker()
    if not client:
        return False
    try:
        pipe = client.pipeline()
        pipe.hdel(_STATUS_KEY, 'error_count', 'last_error', 'last_error_at')
        pipe.hset(_STATUS_KEY, 'errors_reset_at', timezone.now().isoformat())
        pipe.delete(_ERRORS_KEY)
        pipe.execute()
        return True
    except Exception:
        return False


def _as_text(value):
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='replace')
    return str(value)


def watchdog_status_get(include_errors: bool = True) -> dict:
    """Return watcher status; 'available' is False when Redis is not reachable."""
    client = get_redis_from_broker()
    if not client:
        return {'available': False}
    try:
        raw = {_as_text(k): _as_text(v) for k, v in (client.hgetall(_STATUS_KEY) or {}).items()}
        status = {
            'available': True,
            'started_at': raw.get('started_at'),
            'last_heartbeat': raw.get('last_heartbeat'),
            'error_count': int(raw.get('error_count') or 0),
            'last_error': raw.get('last_error') or '',
            'last_error_at': raw.get('last_error_at'),
            'errors_reset_at': raw.get('errors_reset_at'),
            'heartbeat_age_seconds': None,
        }
        if status['last_heartbeat']:
            try:
                from datetime import datetime
                age = (timezone.now() - datetime.fromisoformat(status['last_heartbeat'])).total_seconds()
                status['heartbeat_age_seconds'] = int(age)
            except Exception:
                pass
        if include_errors:
            errors = []
            for item in client.lrange(_ERRORS_KEY, 0, _MAX_RECENT_ERRORS - 1) or []:
                try:
                    errors.append(json.loads(_as_text(item)))
                except Exception:
                    continue
            status['recent_errors'] = errors
        return status
    except Exception as e:
        return {'available': False, 'error': str(e)}


class RedisErrorHandler(logging.Handler):
    """Logging handler that counts ERROR (and above) records in Redis."""

    def __init__(self, level=logging.ERROR):
        super().__init__(level=level)

    def emit(self, record):
        try:
            message = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                exc = record.exc_info[1]
                message = f'{message} [{type(exc).__name__}: {exc}]'
            watchdog_record_error(message, record.name)
        except Exception:
            # Never let bookkeeping break logging
            pass
