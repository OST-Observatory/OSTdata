from __future__ import annotations

import json
import os
import sys
import time as _time
from pathlib import Path
from typing import Dict, Any

from django.db import connection
from django.utils import timezone

try:
    import redis as _redis
except Exception:
    _redis = None
try:
    import django
    _django_version = getattr(django, 'get_version', lambda: '')()
except Exception:
    _django_version = ''
try:
    import ldap as _ldap
except Exception:
    _ldap = None


def gather_admin_health() -> Dict[str, Any]:
    from django.conf import settings
    data: Dict[str, Any] = {}
    data['versions'] = {
        'python': sys.version.split()[0],
        'django': _django_version,
    }
    try:
        import bokeh  # type: ignore
        data['versions']['bokeh'] = getattr(bokeh, '__version__', None) or ''
    except Exception:
        data['versions']['bokeh'] = None
    try:
        data['celery'] = {
            'broker_url': getattr(settings, 'CELERY_BROKER_URL', ''),
            'result_backend': getattr(settings, 'CELERY_RESULT_BACKEND', ''),
            'task_always_eager': bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)),
        }
        data['features'] = {
            'fs_reconcile_enabled': bool(getattr(settings, 'ENABLE_FS_RECONCILE', False)),
            'download_cleanup_enabled': bool(getattr(settings, 'ENABLE_DOWNLOAD_CLEANUP', False)),
        }
    except Exception:
        data['celery'] = {}
        data['features'] = {}

    # DB check
    db_ok = False
    db_latency_ms = None
    try:
        t0 = _time.time()
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        db_latency_ms = int((_time.time() - t0) * 1000)
        db_ok = True
    except Exception as e:
        data['db_error'] = str(e)
    data['database'] = {'ok': db_ok, 'latency_ms': db_latency_ms}

    # Celery ping
    worker_ok = False
    workers = []
    try:
        from ostdata.celery import app as celery_app
        if celery_app:
            insp = celery_app.control.inspect(timeout=1.0)
            pong = insp.ping() or {}
            workers = list(pong.keys())
            worker_ok = len(workers) > 0
    except Exception as e:
        data['celery_ping_error'] = str(e)
    data.setdefault('celery', {})
    data['celery']['workers'] = workers
    data['celery']['workers_alive'] = worker_ok

    # Redis ping
    redis_ok = None
    redis_latency_ms = None
    try:
        broker = data['celery'].get('broker_url') or ''
        if broker.startswith('redis') and _redis:
            from urllib.parse import urlparse
            u = urlparse(broker)
            host = u.hostname or '127.0.0.1'
            port = int(u.port or 6379)
            db = int((u.path or '/0').lstrip('/') or 0)
            password = u.password
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            t0 = _time.time()
            pong = client.ping()
            redis_latency_ms = int((_time.time() - t0) * 1000)
            redis_ok = bool(pong)
    except Exception as e:
        data['redis_error'] = str(e)
    data['redis'] = {'ok': redis_ok, 'latency_ms': redis_latency_ms}

    # Storage summary
    storage = {'ok': None}
    try:
        data_path = os.environ.get('DATA_DIRECTORY', '')
        p = Path(data_path) if data_path else None
        if p:
            exists = p.exists()
            storage['path'] = str(p)
            storage['exists'] = exists
            if exists:
                st = os.statvfs(str(p))
                total = st.f_frsize * st.f_blocks
                free = st.f_frsize * st.f_bavail
                used = total - free
                storage.update({'total_bytes': total, 'used_bytes': used, 'free_bytes': free})
                storage['ok'] = True
            else:
                storage['ok'] = False
    except Exception as e:
        storage['ok'] = False
        storage['error'] = str(e)
    data['storage'] = storage

    # Optional psutil
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        sysinfo = {
            'cpu_percent': float(cpu),
            'memory': {
                'total_bytes': int(vm.total),
                'used_bytes': int(vm.total - vm.available),
                'free_bytes': int(vm.available),
                'percent': float(vm.percent),
            }
        }
        data['system'] = sysinfo
    except Exception:
        data['system'] = None

    return data


