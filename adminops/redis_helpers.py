"""Redis helpers for admin-overridable settings. Avoids circular imports with tasks."""
try:
    import redis as _redis
except Exception:
    _redis = None

_PLATE_SOLVING_TASK_ENABLED_KEY = 'ostdata:admin:plate_solving_task_enabled'
_AUX_OBJECTS_TASK_ENABLED_KEY = 'ostdata:admin:aux_objects_task_enabled'


def get_redis_from_broker():
    try:
        from django.conf import settings
        broker = getattr(settings, 'CELERY_BROKER_URL', '')
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            return _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
    except Exception:
        pass
    return None


def _get_redis_from_broker():
    return get_redis_from_broker()


def plate_solving_task_enabled_get():
    """Get plate solving task enabled from Redis. Returns None if not set (use settings default)."""
    client = _get_redis_from_broker()
    if not client:
        return None
    try:
        raw = client.get(_PLATE_SOLVING_TASK_ENABLED_KEY)
        if raw is None:
            return None
        return raw.decode('utf-8').lower() == 'true'
    except Exception:
        return None


def plate_solving_task_enabled_set(enabled: bool):
    """Set plate solving task enabled in Redis."""
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.set(_PLATE_SOLVING_TASK_ENABLED_KEY, 'true' if enabled else 'false')
        return True
    except Exception:
        return False


def aux_objects_task_enabled_get():
    """Get aux-objects beat task enabled from Redis. None = use settings default."""
    client = _get_redis_from_broker()
    if not client:
        return None
    try:
        raw = client.get(_AUX_OBJECTS_TASK_ENABLED_KEY)
        if raw is None:
            return None
        return raw.decode('utf-8').lower() == 'true'
    except Exception:
        return None


def aux_objects_task_enabled_set(enabled: bool):
    """Set aux-objects beat task enabled in Redis."""
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.set(_AUX_OBJECTS_TASK_ENABLED_KEY, 'true' if enabled else 'false')
        return True
    except Exception:
        return False
