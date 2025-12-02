from pathlib import Path
import os
import json
import sys
import time as _time

from django.db import connection, transaction
from django.utils import timezone
from django.utils.http import http_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
import logging
logger = logging.getLogger(__name__)

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
try:
    from ostdata.celery import app as celery_app
except Exception:
    celery_app = None

from obs_run.tasks import (
    cleanup_expired_downloads,
    reconcile_filesystem,
    cleanup_orphans_and_hashcheck,
    scan_missing_filesystem,
)
from ostdata.services.health import gather_admin_health
from obs_run.models import ObservationRun, DataFile


# -------------------- Banner helpers (Redis) --------------------
_BANNER_REDIS_KEY = 'site:banner'

def _get_redis_from_broker():
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
            client = _redis.Redis(host=host, port=port, db=db, password=password, socket_timeout=1.0)
            return client
    except Exception:
        pass
    return None

def _banner_get():
    client = _get_redis_from_broker()
    if not client:
        return None
    try:
        raw = client.get(_BANNER_REDIS_KEY)
        if not raw:
            return None
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return None
    except Exception:
        return None

def _banner_set(payload: dict):
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.set(_BANNER_REDIS_KEY, json.dumps(payload))
        return True
    except Exception:
        return False

def _banner_clear():
    client = _get_redis_from_broker()
    if not client:
        return False
    try:
        client.delete(_BANNER_REDIS_KEY)
        return True
    except Exception:
        return False


# -------------------- Admin endpoints --------------------

@extend_schema(summary='Admin system health (admin only)', tags=['Admin'])
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_health(request):
    if not (request.user and (request.user.is_superuser or request.user.has_perm('users.acl_system_health_view'))):
        return Response({'detail': 'Forbidden'}, status=403)
    data = gather_admin_health()
    return Response(data, status=200)

@extend_schema(summary='Set observation date (mid JD) for a run', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_run_set_date(request, run_id: int):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    jd = payload.get('jd', None)
    iso = payload.get('iso') or payload.get('datetime') or payload.get('date')
    try:
        run = ObservationRun.objects.get(pk=run_id)
    except ObservationRun.DoesNotExist:
        return Response({'detail': 'Run not found'}, status=404)
    # Compute jd if not provided
    if jd is None and iso:
        try:
            # Prefer astropy if available (authoritative JD conversion)
            try:
                from astropy.time import Time  # type: ignore
                t = Time(str(iso), format='isot', scale='utc') if 'T' in str(iso) else Time(str(iso), format='iso', scale='utc')
                jd = float(t.jd)
            except Exception:
                # Fallback: parse as datetime and convert from Unix epoch
                from datetime import datetime, timezone
                s = str(iso).strip().replace(' ', 'T')
                # Ensure timezone-aware UTC
                dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                unix = dt.timestamp()  # seconds
                jd = unix / 86400.0 + 2440587.5
        except Exception as e:
            return Response({'detail': f'Invalid datetime: {e}'}, status=400)
    if jd is None:
        return Response({'detail': 'jd or iso required'}, status=400)
    try:
        run.mid_observation_jd = float(jd)
        run.save(update_fields=['mid_observation_jd'])
        return Response({'pk': run.pk, 'name': run.name, 'mid_observation_jd': run.mid_observation_jd})
    except Exception as e:
        logger.exception("Failed to set mid_observation_jd for run %s: %s", run_id, e)
        return Response({'detail': str(e)}, status=400)

@extend_schema(summary='Recompute observation date (mid JD) from files', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_run_recompute_date(request, run_id: int):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        run = ObservationRun.objects.get(pk=run_id)
    except ObservationRun.DoesNotExist:
        return Response({'detail': 'Run not found'}, status=404)
    try:
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
        return Response({'pk': run.pk, 'name': run.name, 'mid_observation_jd': run.mid_observation_jd})
    except Exception as e:
        logger.exception("Failed to recompute mid_observation_jd for run %s: %s", run_id, e)
        return Response({'detail': str(e)}, status=400)

class AdminReconcileRequestSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(required=False, default=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger cleanup of expired downloads', request=None, responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_cleanup_downloads(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_cleanup')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        res = cleanup_expired_downloads.delay()
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None)}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_cleanup_downloads failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger filesystem reconcile', request=AdminReconcileRequestSerializer, responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_reconcile(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        dry_run = bool(request.data.get('dry_run', True)) if hasattr(request, 'data') else True
    except Exception:
        dry_run = True
    try:
        res = reconcile_filesystem.delay(dry_run=dry_run)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_reconcile failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


class AdminOrphansRequestSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(required=False, default=True)
    fix_missing_hashes = serializers.BooleanField(required=False, default=True)
    limit = serializers.IntegerField(required=False, allow_null=True)


class AdminScanMissingRequestSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(required=False, default=True)
    limit = serializers.IntegerField(required=False, allow_null=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger orphans cleanup/hashcheck', request=AdminOrphansRequestSerializer, responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_orphans_hashcheck(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_orphans')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    try:
        dry_run = bool(payload.get('dry_run', True))
    except Exception:
        dry_run = True
    try:
        fix_missing_hashes = bool(payload.get('fix_missing_hashes', True))
    except Exception:
        fix_missing_hashes = True
    try:
        limit = payload.get('limit', None)
        limit = int(limit) if (limit is not None and str(limit).strip() != '') else None
    except Exception:
        limit = None
    try:
        res = cleanup_orphans_and_hashcheck.delay(dry_run=dry_run, fix_missing_hashes=fix_missing_hashes, limit=limit)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_orphans_hashcheck failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger scan for missing files (ingest new files from filesystem)', request=AdminScanMissingRequestSerializer, responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_scan_missing(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    try:
        dry_run = bool(payload.get('dry_run', True))
    except Exception:
        dry_run = True
    try:
        limit = payload.get('limit', None)
        limit = int(limit) if (limit is not None and str(limit).strip() != '') else None
    except Exception:
        limit = None
    try:
        res = scan_missing_filesystem.delay(dry_run=dry_run, limit=limit)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run, 'limit': limit}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_scan_missing failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)

class AdminBannerSetSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False, default=True)
    message = serializers.CharField(required=False, allow_blank=True, default='')
    level = serializers.ChoiceField(choices=['info', 'success', 'warning', 'error'], required=False, default='warning')


@extend_schema(summary='Admin banner: get current banner', tags=['Admin'])
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_banner(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    data = _banner_get() or {'enabled': False, 'message': '', 'level': 'warning'}
    return Response(data)


@extend_schema(summary='Admin banner: set banner', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(request=AdminBannerSetSerializer, responses={'200': {'type': 'object'}})
def admin_set_banner(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    body = request.data if hasattr(request, 'data') else {}
    enabled = bool(body.get('enabled', True))
    message = str(body.get('message', '') or '')
    level = str(body.get('level', 'warning') or 'warning')
    payload = {'enabled': enabled, 'message': message, 'level': level}
    ok = _banner_set(payload)
    if not ok:
        logger.error("Failed to persist banner payload: %s", payload)
        return Response({'error': 'Failed to persist banner'}, status=500)
    return Response(payload)


@extend_schema(summary='Admin banner: clear banner', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_clear_banner(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_banner_manage')):
        return Response({'detail': 'Forbidden'}, status=403)
    ok = _banner_clear()
    if not ok:
        logger.error("Failed to clear banner")
        return Response({'error': 'Failed to clear banner'}, status=500)
    return Response({'cleared': True})


@extend_schema(summary='Public banner info', tags=['Admin'])
@api_view(['GET'])
@permission_classes([AllowAny])
def banner_info(request):
    data = _banner_get() or {'enabled': False, 'message': '', 'level': 'warning'}
    return Response(data)




