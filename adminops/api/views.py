from pathlib import Path
import os
import json
import sys
import time as _time

from django.db import connection, transaction
from django.utils import timezone
from django.utils.http import http_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from ostdata.permissions import IsAdminOrSuperuser as IsAdminUser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
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
    cleanup_orphan_objects,
    unlink_non_light_datafiles_from_objects,
    plate_solve_pending_files,
    re_evaluate_plate_solved_files,
)
from ostdata.services.health import gather_admin_health
from obs_run.models import ObservationRun, DataFile
from obs_run.api.serializers import DataFileSerializer
from obs_run.api.views import DataFilesPagination
from objects.models import Object, Identifier
from utilities import (
    _query_object_variants, 
    _query_region_safe, 
    update_observation_run_photometry_spectroscopy, 
    update_object_photometry_spectroscopy, 
    annotate_effective_exposure_type, 
    evaluate_data_file, 
    reanalyse_object_from_simbad
)
from obs_run.utils import should_allow_auto_update
from obs_run.plate_solving import PlateSolvingService, solve_and_update_datafile
from django.db.models import Q, F, Count, Case, When, Value
from django.db.models import CharField


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


# Plate Solving Task: use redis_helpers to avoid circular imports with obs_run.tasks
from adminops.redis_helpers import (
    plate_solving_task_enabled_get as _plate_solving_task_enabled_get,
    plate_solving_task_enabled_set as _plate_solving_task_enabled_set,
)


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
        from obs_run.utils import check_and_set_override, get_override_field_name
        old_jd = run.mid_observation_jd
        run.mid_observation_jd = float(jd)
        override_fields = ['mid_observation_jd']
        if check_and_set_override(run, 'mid_observation_jd', run.mid_observation_jd, old_jd):
            override_fields.append(get_override_field_name('mid_observation_jd'))
        run.save(update_fields=override_fields)
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

@extend_schema(summary='Clear override flag for a specific field', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_clear_override_flag(request, model_type: str, instance_id: int, field_name: str):
    """
    Clear a single override flag for a specific field.
    model_type: 'run', 'datafile', or 'object'
    instance_id: ID of the instance
    field_name: Name of the field (e.g., 'mid_observation_jd')
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
        return Response({'detail': 'Forbidden'}, status=403)
    
    from obs_run.utils import get_override_field_name
    
    # Map model types
    model_map = {
        'run': ObservationRun,
        'datafile': DataFile,
        'object': Object,
    }
    
    if model_type.lower() not in model_map:
        return Response({'detail': f'Invalid model_type: {model_type}'}, status=400)
    
    model_class = model_map[model_type.lower()]
    
    try:
        instance = model_class.objects.get(pk=instance_id)
    except model_class.DoesNotExist:
        return Response({'detail': f'{model_type} not found'}, status=404)
    
    override_field_name = get_override_field_name(field_name)
    if not hasattr(instance, override_field_name):
        return Response({'detail': f'Override field {override_field_name} does not exist'}, status=400)
    
    try:
        setattr(instance, override_field_name, False)
        instance.save(update_fields=[override_field_name])
        return Response({
            'success': True,
            'model_type': model_type,
            'instance_id': instance_id,
            'field_name': field_name,
            'override_flag': override_field_name,
        })
    except Exception as e:
        logger.exception("Failed to clear override flag: %s", e)
        return Response({'detail': str(e)}, status=400)

@extend_schema(summary='Clear all override flags for an instance', tags=['Admin'])
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_clear_all_overrides(request, model_type: str, instance_id: int):
    """
    Clear all override flags for a specific instance.
    model_type: 'run', 'datafile', or 'object'
    instance_id: ID of the instance
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
        return Response({'detail': 'Forbidden'}, status=403)
    
    from obs_run.utils import get_override_field_name
    
    # Map model types and their overrideable fields
    model_configs = {
        'run': {
            'model': ObservationRun,
            'fields': ['name', 'is_public', 'reduction_status', 'photometry', 
                      'spectroscopy', 'note', 'mid_observation_jd'],
        },
        'datafile': {
            'model': DataFile,
            'fields': ['exposure_type', 'spectroscopy', 'spectrograph', 
                      'instrument', 'telescope', 'status_parameters'],
        },
        'object': {
            'model': Object,
            'fields': ['name', 'is_public', 'ra', 'dec', 'first_hjd', 
                      'is_main', 'photometry', 'spectroscopy', 
                      'simbad_resolved', 'object_type', 'note'],
        },
    }
    
    if model_type.lower() not in model_configs:
        return Response({'detail': f'Invalid model_type: {model_type}'}, status=400)
    
    config = model_configs[model_type.lower()]
    model_class = config['model']
    fields = config['fields']
    
    try:
        instance = model_class.objects.get(pk=instance_id)
    except model_class.DoesNotExist:
        return Response({'detail': f'{model_type} not found'}, status=404)
    
    cleared_flags = []
    update_fields = []
    
    for field_name in fields:
        override_field_name = get_override_field_name(field_name)
        if hasattr(instance, override_field_name):
            current_value = getattr(instance, override_field_name, False)
            if current_value:
                setattr(instance, override_field_name, False)
                update_fields.append(override_field_name)
                cleared_flags.append(field_name)
    
    if update_fields:
        instance.save(update_fields=update_fields)
    
    return Response({
        'success': True,
        'model_type': model_type,
        'instance_id': instance_id,
        'cleared_flags': cleared_flags,
        'count': len(cleared_flags),
    })

@extend_schema(summary='List all instances with override flags', tags=['Admin'])
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_list_override_flags(request):
    """
    List all instances (runs, datafiles, objects) that have any override flags set.
    Returns a summary grouped by model type.
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_runs_edit')):
        return Response({'detail': 'Forbidden'}, status=403)
    
    from obs_run.utils import get_override_field_name
    
    # Map model types and their overrideable fields
    model_configs = {
        'run': {
            'model': ObservationRun,
            'fields': ['name', 'is_public', 'reduction_status', 'photometry', 
                      'spectroscopy', 'note', 'mid_observation_jd'],
            'name_field': 'name',
        },
        'datafile': {
            'model': DataFile,
            'fields': ['exposure_type', 'spectroscopy', 'spectrograph', 
                      'instrument', 'telescope', 'status_parameters'],
            'name_field': 'datafile',
        },
        'object': {
            'model': Object,
            'fields': ['name', 'is_public', 'ra', 'dec', 'first_hjd', 
                      'is_main', 'photometry', 'spectroscopy', 
                      'simbad_resolved', 'object_type', 'note'],
            'name_field': 'name',
        },
    }
    
    result = {}
    
    for model_type, config in model_configs.items():
        model_class = config['model']
        fields = config['fields']
        name_field = config['name_field']
        
        # Build Q filter for any override flag being True
        from django.db.models import Q
        override_filters = Q()
        for field_name in fields:
            override_field_name = get_override_field_name(field_name)
            if hasattr(model_class, override_field_name):
                override_filters |= Q(**{override_field_name: True})
        
        # Get instances with any override flags
        instances = model_class.objects.filter(override_filters).select_related()[:100]  # Limit to 100 for performance
        
        items = []
        for instance in instances:
            override_fields = []
            for field_name in fields:
                override_field_name = get_override_field_name(field_name)
                if hasattr(instance, override_field_name):
                    if getattr(instance, override_field_name, False):
                        override_fields.append(field_name)
            
            if override_fields:
                items.append({
                    'id': instance.pk,
                    'name': getattr(instance, name_field, str(instance.pk)),
                    'override_fields': override_fields,
                })
        
        result[model_type] = {
            'count': len(items),
            'items': items,
        }
    
    return Response(result)

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


class AdminOrphanObjectsRequestSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(required=False, default=True)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(
    summary='Cleanup orphan Objects (no DataFiles)',
    description='Finds and removes Objects that have no associated DataFiles. Also recalculates first_hjd and cleans stale observation_run M2M links.',
    request=AdminOrphanObjectsRequestSerializer,
    responses={'202': {'type': 'object'}},
    tags=['Admin']
)
def admin_trigger_orphan_objects(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_orphans')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    try:
        dry_run = bool(payload.get('dry_run', True))
    except Exception:
        dry_run = True
    try:
        res = cleanup_orphan_objects.delay(dry_run=dry_run)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_orphan_objects failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(
    summary='Unlink non-Light DataFiles from Objects',
    description='Removes Object–DataFile associations for all DataFiles that are not Light frames (flats, darks, bias, etc.).',
    request=AdminOrphanObjectsRequestSerializer,
    responses={'202': {'type': 'object'}},
    tags=['Admin']
)
def admin_trigger_unlink_non_light_datafiles(request):
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_orphans')):
        return Response({'detail': 'Forbidden'}, status=403)
    payload = request.data if hasattr(request, 'data') else {}
    try:
        dry_run = bool(payload.get('dry_run', True))
    except Exception:
        dry_run = True
    try:
        res = unlink_non_light_datafiles_from_objects.delay(dry_run=dry_run)
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None), 'dry_run': dry_run}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_unlink_non_light_datafiles failed: %s", e)
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


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger dashboard stats refresh', responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_refresh_dashboard_stats(request):
    """
    Manually trigger a background refresh of dashboard statistics.
    The stats are cached for 30 minutes, storage size for 2 hours.
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        from obs_run.tasks import refresh_dashboard_stats
        res = refresh_dashboard_stats.delay()
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None)}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_refresh_dashboard_stats failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(summary='Trigger plate solving', responses={'202': {'type': 'object'}}, tags=['Admin'])
def admin_trigger_plate_solve_task(request):
    """
    Manually trigger plate solving for pending files.
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        res = plate_solve_pending_files.delay()
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None)}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_plate_solve_task failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@api_view(['POST'])
@permission_classes([IsAdminUser])
@extend_schema(
    summary='Re-evaluate plate-solved files',
    description='Re-run object association for plate-solved files where header had no coords or WCS differs from header by > threshold.',
    responses={'202': {'type': 'object'}},
    tags=['Admin']
)
def admin_trigger_re_evaluate_plate_solved(request):
    """
    Manually trigger re-evaluation of plate-solved files (evaluate_data_file).
    """
    if not (request.user.is_superuser or request.user.has_perm('users.acl_maintenance_reconcile')):
        return Response({'detail': 'Forbidden'}, status=403)
    try:
        res = re_evaluate_plate_solved_files.delay()
        return Response({'enqueued': True, 'task_id': getattr(res, 'id', None)}, status=202)
    except Exception as e:
        logger.exception("admin_trigger_re_evaluate_plate_solved failed: %s", e)
        return Response({'enqueued': False, 'error': str(e)}, status=400)


@extend_schema(
    summary='Delete all aliases (identifiers) for an object',
    description='Removes all non-header-based identifiers (aliases) for the given object.',
    responses={200: serializers.Serializer}
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_delete_object_aliases(request, object_id):
    """Delete all identifiers where info_from_header=False for the given object."""
    try:
        obj = Object.objects.get(pk=object_id)
    except Object.DoesNotExist:
        return Response({'error': 'Object not found'}, status=404)
    except Exception as e:
        logger.exception(f'Error fetching object {object_id}: {e}')
        return Response({'error': f'Error fetching object: {str(e)}'}, status=500)
    try:
        deleted_count = obj.identifier_set.filter(info_from_header=False).delete()[0]
        return Response({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} alias(es).',
        })
    except Exception as e:
        logger.exception(f'Error deleting aliases for object {object_id}: {e}')
        return Response({'error': str(e)}, status=500)


@extend_schema(
    summary='Update object identifiers from SIMBAD',
    description='Query SIMBAD and update identifiers for an object. Supports matching by name or coordinates.',
    request=serializers.Serializer,
    responses={200: serializers.Serializer}
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_update_object_identifiers(request, object_id):
    """
    Update object identifiers from SIMBAD.
    
    Query parameters:
    - match_method: 'name' or 'coordinates' (default: 'name')
    - dry_run: 'true' or 'false' (default: 'false')
    """
    try:
        obj = Object.objects.get(pk=object_id)
    except Object.DoesNotExist:
        return Response({'error': 'Object not found'}, status=404)
    except Exception as e:
        logger.exception(f'Error fetching object {object_id}: {e}')
        return Response({'error': f'Error fetching object: {str(e)}'}, status=500)
    
    try:
        match_method = request.data.get('match_method', 'name')
        dry_run = request.data.get('dry_run', 'false')
        dry_run = str(dry_run).lower() in ('true', '1', 'yes')
        
        # Get current identifiers (excluding header-based ones)
        try:
            current_identifiers = list(
                obj.identifier_set.filter(info_from_header=False).values_list('name', flat=True)
            )
        except Exception as e:
            logger.exception(f'Error fetching current identifiers for object {object_id}: {e}')
            current_identifiers = []
        
        simbad_table = None
        error_message = None
        
        try:
            if match_method == 'name':
                # Query by object name
                if not obj.name or not obj.name.strip():
                    error_message = 'Object name is empty, cannot query SIMBAD by name'
                else:
                    simbad_table = _query_object_variants(obj.name)
                    if simbad_table is None or len(simbad_table) == 0:
                        error_message = f'No SIMBAD result found for name: {obj.name}'
            elif match_method == 'coordinates':
                # Query by coordinates
                if obj.ra == -1 or obj.dec == -1 or obj.ra == 0 or obj.dec == 0:
                    error_message = 'Invalid coordinates for SIMBAD query'
                else:
                    simbad_table = _query_region_safe(obj.ra, obj.dec, '0d5m0s', row_limit=10)
                    if simbad_table is None or len(simbad_table) == 0:
                        error_message = f'No SIMBAD result found for coordinates: RA={obj.ra}, Dec={obj.dec}'
                    elif len(simbad_table) > 0:
                        # Use first result (closest match)
                        simbad_table = simbad_table[:1]
            else:
                return Response({'error': f'Invalid match_method: {match_method}'}, status=400)
        except Exception as e:
            logger.exception(f'Error querying SIMBAD for object {object_id}: {e}')
            error_message = f'SIMBAD query failed: {str(e)}'
        
        if error_message:
            return Response({
                'error': error_message,
                'current_identifiers': current_identifiers,
                'new_identifiers': [],
                'identifiers_to_delete': current_identifiers,
                'identifiers_to_create': [],
            })
        
        if simbad_table is None or len(simbad_table) == 0:
            return Response({
                'error': 'No SIMBAD results found',
                'current_identifiers': current_identifiers,
                'new_identifiers': [],
                'identifiers_to_delete': current_identifiers,
                'identifiers_to_create': [],
            })
        
        # Extract identifiers from SIMBAD result
        try:
            row = simbad_table[0]
        except (IndexError, KeyError, TypeError) as e:
            logger.exception(f'Error accessing SIMBAD table row for object {object_id}: {e}')
            return Response({
                'error': f'Error processing SIMBAD results: {str(e)}',
                'current_identifiers': current_identifiers,
                'new_identifiers': [],
                'identifiers_to_delete': current_identifiers,
                'identifiers_to_create': [],
            })
        
        # Get main_id first
        main_id = None
        try:
            main_id = row.get('main_id', None)
            if main_id is not None:
                main_id = str(main_id).strip()
        except Exception as e:
            logger.debug(f'Error extracting main_id: {e}')
            pass
        
        # Get all identifiers from IDS field
        aliases_field = None
        try:
            aliases_field = row['IDS']
        except (KeyError, IndexError):
            try:
                aliases_field = row['ids']
            except (KeyError, IndexError):
                try:
                    # Try accessing by index if it's a table row
                    aliases_field = row[3] if len(row) > 3 else None  # IDS is often column 3
                except Exception:
                    aliases_field = None
        
        aliases = []
        if aliases_field is not None:
            try:
                # Handle both string and masked array formats
                aliases_str = str(aliases_field)
                # Split by pipe character and clean up
                aliases = [a.strip() for a in aliases_str.split('|') if a and a.strip()]
            except Exception as e:
                logger.debug(f'Error parsing aliases field: {e}')
                aliases = []
        
        # Add main_id to the list if it's not already there
        if main_id and main_id not in aliases:
            aliases.insert(0, main_id)
        elif not main_id and aliases:
            # If no main_id but we have aliases, use first alias as main
            pass
        
        # Remove duplicates while preserving order
        new_identifiers = []
        seen = set()
        for alias in aliases:
            try:
                alias_clean = alias.strip()
                if alias_clean and alias_clean not in seen:
                    seen.add(alias_clean)
                    new_identifiers.append(alias_clean)
            except Exception as e:
                logger.debug(f'Error processing alias: {e}')
                continue
        
        # Create SIMBAD href
        try:
            object_name = str(main_id) if main_id else (obj.name if obj.name else 'unknown')
            sanitized_name = object_name.replace(" ", "").replace('+', "%2B")
            simbad_href = f"https://simbad.u-strasbg.fr/simbad/sim-id?Ident={sanitized_name}"
        except Exception as e:
            logger.debug(f'Error creating SIMBAD href: {e}')
            simbad_href = None
        
        # Determine what would change
        identifiers_to_delete = current_identifiers
        identifiers_to_create = new_identifiers
        
        if not dry_run:
            # Actually update identifiers
            try:
                with transaction.atomic():
                    # Delete all existing identifiers (excluding header-based ones)
                    deleted_count = obj.identifier_set.filter(info_from_header=False).delete()[0]
                    
                    # Create new identifiers from SIMBAD
                    created_count = 0
                    for alias in new_identifiers:
                        try:
                            Identifier.objects.create(
                                obj=obj,
                                name=alias,
                                href=simbad_href,
                                info_from_header=False,
                            )
                            created_count += 1
                        except Exception as e:
                            logger.exception(f'Error creating identifier "{alias}" for object {object_id}: {e}')
                            # Continue with other identifiers even if one fails
                            continue
                    
                    return Response({
                        'success': True,
                        'message': f'Updated identifiers: deleted {deleted_count}, created {created_count}',
                        'current_identifiers': new_identifiers,
                        'previous_identifiers': current_identifiers,
                        'identifiers_deleted': deleted_count,
                        'identifiers_created': created_count,
                    })
            except Exception as e:
                logger.exception(f'Error updating identifiers for object {object_id}: {e}')
                return Response({
                    'error': f'Error updating identifiers: {str(e)}',
                    'current_identifiers': current_identifiers,
                    'new_identifiers': new_identifiers,
                }, status=500)
        else:
            # Dry-run: just return what would change
            return Response({
                'success': True,
                'dry_run': True,
                'message': f'Would delete {len(identifiers_to_delete)} and create {len(identifiers_to_create)} identifiers',
                'current_identifiers': current_identifiers,
                'new_identifiers': new_identifiers,
                'identifiers_to_delete': identifiers_to_delete,
                'identifiers_to_create': identifiers_to_create,
                'simbad_main_id': main_id if main_id else None,
                'simbad_href': simbad_href,
            })
    except Exception as e:
        logger.exception(f'Unexpected error in admin_update_object_identifiers for object {object_id}: {e}')
        return Response({
            'error': f'Unexpected error: {str(e)}',
        }, status=500)


@extend_schema(
    summary='Re-analyse object from SIMBAD (coordinates)',
    description='Query SIMBAD by object coordinates, update name, object_type, and identifiers. '
                'If classified as star, verifies with extended search (default 10 arcmin). '
                'Propagates name changes to associated DataFiles.',
    request=serializers.Serializer,
    responses={200: serializers.Serializer}
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_reanalyse_object(request, object_id):
    """
    Re-analyse object from SIMBAD based on coordinates.
    Updates: name (main_id), object_type, identifiers.
    If object_type is ST, runs star verification (extended search, default 10 arcmin FOV).
    Propagates name changes to associated DataFiles.
    """
    try:
        obj = Object.objects.get(pk=object_id)
    except Object.DoesNotExist:
        return Response({'success': False, 'error': 'Object not found'}, status=404)
    except Exception as e:
        logger.exception(f'Error fetching object {object_id}: {e}')
        return Response({'success': False, 'error': str(e)}, status=500)

    try:
        fixed_radius = request.data.get('fixed_radius_arcmin', 10.0)
        try:
            fixed_radius = float(fixed_radius)
        except (TypeError, ValueError):
            fixed_radius = 10.0
        dry_run = request.data.get('dry_run', False)
        dry_run = str(dry_run).lower() in ('true', '1', 'yes')

        result = reanalyse_object_from_simbad(obj, fixed_radius_arcmin=fixed_radius, dry_run=dry_run)
        if result.get('success'):
            return Response(result)
        return Response(result, status=400)
    except Exception as e:
        logger.exception(f'Reanalyse failed for object {object_id}: {e}')
        return Response({'success': False, 'error': str(e)}, status=500)


@extend_schema(
    summary='Get exposure type discrepancies',
    parameters=[
        OpenApiParameter('header_type', str, OpenApiParameter.QUERY, description='Filter by header exposure type'),
        OpenApiParameter('ml_type', str, OpenApiParameter.QUERY, description='Filter by ML exposure type'),
        OpenApiParameter('observation_run', int, OpenApiParameter.QUERY, description='Filter by observation run ID'),
        OpenApiParameter('observation_run_name', str, OpenApiParameter.QUERY, description='Filter by observation run name (case-insensitive partial match)'),
        OpenApiParameter('has_user_type', bool, OpenApiParameter.QUERY, description='Filter by presence of user-set type'),
        OpenApiParameter('file_name', str, OpenApiParameter.QUERY, description='Filter by file name (case-insensitive partial match)'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_exposure_type_discrepancies(request):
    """
    Get DataFiles where header-based exposure_type differs from ML-classified exposure_type_ml.
    Only accessible to admin/staff users.
    Supports filtering by header_type, ml_type, observation_run, and has_user_type.
    """
    # Get files where:
    # 1. exposure_type_ml is NULL (not yet classified), OR
    # 2. exposure_type_ml is empty string, OR
    # 3. exposure_type_ml is 'UK' (Unknown), OR
    # 4. exposure_type != exposure_type_ml (discrepancy)
    queryset = DataFile.objects.filter(
        Q(exposure_type_ml__isnull=True) | 
        Q(exposure_type_ml='') | 
        Q(exposure_type_ml='UK') | 
        ~Q(exposure_type=F('exposure_type_ml'))
    ).select_related('observation_run')

    # Filter by header_type
    header_type = request.query_params.get('header_type')
    if header_type:
        queryset = queryset.filter(exposure_type=header_type)

    # Filter by ml_type
    ml_type = request.query_params.get('ml_type')
    if ml_type:
        queryset = queryset.filter(exposure_type_ml=ml_type)

    # Filter by observation_run (by ID or name)
    observation_run_id = request.query_params.get('observation_run')
    observation_run_name = request.query_params.get('observation_run_name')
    if observation_run_id:
        try:
            queryset = queryset.filter(observation_run_id=int(observation_run_id))
        except ValueError:
            pass
    elif observation_run_name:
        queryset = queryset.filter(observation_run__name__icontains=observation_run_name)

    # Filter by has_user_type
    has_user_type = request.query_params.get('has_user_type')
    if has_user_type is not None:
        has_user_type_bool = str(has_user_type).lower() in ('true', '1', 'yes')
        if has_user_type_bool:
            queryset = queryset.exclude(Q(exposure_type_user__isnull=True) | Q(exposure_type_user=''))
        else:
            queryset = queryset.filter(Q(exposure_type_user__isnull=True) | Q(exposure_type_user=''))

    # Filter by file_name (case-insensitive partial match on datafile path)
    file_name = request.query_params.get('file_name')
    if file_name:
        queryset = queryset.filter(datafile__icontains=file_name)

    # Pagination
    paginator = DataFilesPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = DataFileSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = DataFileSerializer(queryset, many=True)
    return Response(serializer.data)


@extend_schema(
    summary='Update user-set exposure type',
    parameters=[
        OpenApiParameter('pk', int, OpenApiParameter.PATH),
    ],
)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def admin_update_exposure_type_user(request, pk):
    """
    Update the user-set exposure_type_user for a DataFile.
    Only accessible to admin/staff users.
    
    Body:
    {
        "exposure_type_user": "LI",
        "exposure_type_user_override": true
    }
    """
    try:
        datafile = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    exposure_type_user = request.data.get('exposure_type_user')
    exposure_type_user_override = request.data.get('exposure_type_user_override', False)

    # Validate exposure_type_user
    if exposure_type_user is not None:
        valid_types = [choice[0] for choice in DataFile.EXPOSURE_TYPE_POSSIBILITIES]
        if exposure_type_user not in valid_types:
            return Response(
                {"detail": f"Invalid exposure_type_user. Must be one of: {valid_types}"},
                status=400
            )
        datafile.exposure_type_user = exposure_type_user
    elif exposure_type_user is None and 'exposure_type_user' in request.data:
        # Explicitly set to None to clear the value
        datafile.exposure_type_user = None

    # Update override flag
    if isinstance(exposure_type_user_override, bool):
        datafile.exposure_type_user_override = exposure_type_user_override

    datafile.save(update_fields=['exposure_type_user', 'exposure_type_user_override'])

    # Re-evaluate object association when set to Light (LI) so coordinate-based
    # resolution can run for files that were previously misclassified
    if exposure_type_user == 'LI' and datafile.observation_run:
        try:
            evaluate_data_file(
                datafile,
                datafile.observation_run,
                skip_if_object_has_overrides=True,
            )
            update_observation_run_photometry_spectroscopy(datafile.observation_run)
            for obj in datafile.object_set.all():
                update_object_photometry_spectroscopy(obj)
        except Exception as e:
            logger.warning(f'Re-evaluation after exposure_type_user=LI failed for datafile {datafile.pk}: {e}')
        datafile.refresh_from_db()

    serializer = DataFileSerializer(datafile)
    return Response(serializer.data)


@extend_schema(
    summary='Get DataFiles for spectrograph management',
    parameters=[
        OpenApiParameter('spectrograph', str, OpenApiParameter.QUERY, description='Filter by spectrograph type'),
        OpenApiParameter('exposure_type', str, OpenApiParameter.QUERY, description='Filter by exposure type'),
        OpenApiParameter('observation_run', int, OpenApiParameter.QUERY, description='Filter by observation run ID'),
        OpenApiParameter('observation_run_name', str, OpenApiParameter.QUERY, description='Filter by observation run name (case-insensitive partial match)'),
        OpenApiParameter('file_name', str, OpenApiParameter.QUERY, description='Filter by file name (case-insensitive partial match)'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_spectrograph_files(request):
    """
    Get DataFiles where spectrograph is set or exposure_type is WAVE.
    Only accessible to admin/staff users.
    Supports filtering by spectrograph, exposure_type, observation_run, and file_name.
    """
    # Get files where:
    # 1. spectrograph is set (not 'N' / NONE), OR
    # 2. exposure_type is 'WAVE'
    queryset = DataFile.objects.filter(
        Q(spectrograph__in=['D', 'B', 'E']) | Q(exposure_type='WA')
    ).select_related('observation_run')

    # Filter by spectrograph
    spectrograph = request.query_params.get('spectrograph')
    if spectrograph:
        queryset = queryset.filter(spectrograph=spectrograph)

    # Filter by exposure_type
    exposure_type = request.query_params.get('exposure_type')
    if exposure_type:
        queryset = queryset.filter(exposure_type=exposure_type)

    # Filter by observation_run (by ID or name)
    observation_run_id = request.query_params.get('observation_run')
    observation_run_name = request.query_params.get('observation_run_name')
    if observation_run_id:
        try:
            queryset = queryset.filter(observation_run_id=int(observation_run_id))
        except ValueError:
            pass
    elif observation_run_name:
        queryset = queryset.filter(observation_run__name__icontains=observation_run_name)

    # Filter by file_name (case-insensitive partial match on datafile path)
    file_name = request.query_params.get('file_name')
    if file_name:
        queryset = queryset.filter(datafile__icontains=file_name)

    # Pagination
    paginator = DataFilesPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = DataFileSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    serializer = DataFileSerializer(queryset, many=True)
    return Response(serializer.data)


@extend_schema(
    summary='Update spectrograph property',
    parameters=[
        OpenApiParameter('pk', int, OpenApiParameter.PATH),
    ],
)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])
def admin_update_spectrograph(request, pk):
    """
    Update the spectrograph property for a DataFile.
    Only accessible to admin/staff users.
    
    Body:
    {
        "spectrograph": "D",
        "spectrograph_override": true
    }
    """
    try:
        datafile = DataFile.objects.get(pk=pk)
    except DataFile.DoesNotExist:
        return Response({"detail": "Not found"}, status=404)

    spectrograph = request.data.get('spectrograph')
    spectrograph_override = request.data.get('spectrograph_override', False)

    # Validate spectrograph
    if spectrograph is not None:
        valid_spectrographs = [choice[0] for choice in DataFile.spectrograph_possibilities]
        if spectrograph not in valid_spectrographs:
            return Response(
                {"detail": f"Invalid spectrograph. Must be one of: {valid_spectrographs}"},
                status=400
            )
        datafile.spectrograph = spectrograph
    elif spectrograph is None and 'spectrograph' in request.data:
        # Explicitly set to 'N' (NONE) to clear the value
        datafile.spectrograph = 'N'

    # Update override flag
    if isinstance(spectrograph_override, bool):
        datafile.spectrograph_override = spectrograph_override

    datafile.save(update_fields=['spectrograph', 'spectrograph_override'])

    # Automatically update photometry/spectroscopy flags for associated observation runs and objects
    # Update observation run
    if datafile.observation_run:
        update_observation_run_photometry_spectroscopy(datafile.observation_run)
    
    # Update all associated objects
    for obj in datafile.object_set.all():
        update_object_photometry_spectroscopy(obj)

    serializer = DataFileSerializer(datafile)
    return Response(serializer.data)


@extend_schema(
    summary='Get unsolved plate files',
    parameters=[
        OpenApiParameter('observation_run', int, OpenApiParameter.QUERY, description='Filter by observation run ID'),
        OpenApiParameter('file_name', str, OpenApiParameter.QUERY, description='Filter by file name (case-insensitive partial match)'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_unsolved_plate_files(request):
    """
    Get DataFiles where plate_solved=False.
    Only accessible to admin/staff users.
    Supports filtering by observation_run and file_name.
        Only shows Light frames (effective_exposure_type='LI'), excluding spectra.
    """
    # Base queryset: exclude spectra
    queryset = DataFile.objects.filter(
        spectrograph='N',  # Exclude spectra (only show files without spectrograph)
        spectroscopy=False  # Exclude files marked as spectroscopy
    ).select_related('observation_run')
    
    # Annotate with effective_exposure_type and filter for Light frames only
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
    
    # Apply additional filters (after annotation so they work correctly)
    # Filter by observation_run (by ID or name)
    observation_run_id = request.query_params.get('observation_run')
    observation_run_name = request.query_params.get('observation_run_name')
    if observation_run_id:
        try:
            queryset = queryset.filter(observation_run_id=int(observation_run_id))
        except ValueError:
            pass
    elif observation_run_name:
        queryset = queryset.filter(observation_run__name__icontains=observation_run_name)
    
    # Filter by file_name (case-insensitive partial match on datafile path)
    file_name = request.query_params.get('file_name')
    if file_name:
        queryset = queryset.filter(datafile__icontains=file_name)
    
    # Filter by instrument
    instrument = request.query_params.get('instrument')
    if instrument:
        queryset = queryset.filter(instrument__icontains=instrument)
    
    # Filter by file_type
    file_type = request.query_params.get('file_type')
    if file_type:
        queryset = queryset.filter(file_type__iexact=file_type)
    
    # Filter by plate solving status
    # 'solved': plate_solved=True
    # 'unsolved': plate_solved=False
    # 'attempted': plate_solve_attempted_at is not null
    # 'error': plate_solve_error is not null
    status_filter = request.query_params.get('status')
    if status_filter:
        if status_filter == 'solved':
            queryset = queryset.filter(plate_solved=True)
        elif status_filter == 'unsolved':
            queryset = queryset.filter(plate_solved=False)
        elif status_filter == 'attempted':
            queryset = queryset.filter(plate_solve_attempted_at__isnull=False)
        elif status_filter == 'error':
            queryset = queryset.filter(plate_solve_error__isnull=False)
    
    # Legacy: if no status filter, default to unsolved (for backward compatibility)
    if not status_filter:
        queryset = queryset.filter(plate_solved=False)
    
    # Apply sorting (default: pk ascending for reproducible pagination)
    sort_by = request.query_params.get('sort_by', 'pk')
    sort_order = request.query_params.get('sort_order', 'asc')
    
    # Validate sort_by field (prevent SQL injection)
    allowed_sort_fields = ['pk', 'datafile', 'observation_run', 'instrument', 'file_type', 
                          'plate_solve_attempted_at', 'obs_date']
    if sort_by not in allowed_sort_fields:
        sort_by = 'pk'
    
    # Apply sorting
    if sort_order.lower() == 'desc':
        queryset = queryset.order_by(f'-{sort_by}', 'pk')  # Always include pk for stable sorting
    else:
        queryset = queryset.order_by(sort_by, 'pk')  # Always include pk for stable sorting
    
    # Pagination
    paginator = DataFilesPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = DataFileSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    serializer = DataFileSerializer(queryset, many=True)
    return Response(serializer.data)


@extend_schema(
    summary='Get list of observation runs for plate solving filter',
    parameters=[],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_observation_runs_for_plate_solving(request):
    """
    Get list of observation runs that have Light frames (for plate solving filter dropdown).
    Only accessible to admin/staff users.
    """
    from django.db.models import Subquery, OuterRef

    # Get the first obs_date from datafiles of each run (for display)
    first_obs_date = DataFile.objects.filter(
        observation_run_id=OuterRef('pk')
    ).order_by('pk').values('obs_date')[:1]

    # Get observation runs that have Light frames (excluding spectra)
    queryset = ObservationRun.objects.filter(
        datafile__spectrograph='N',
        datafile__spectroscopy=False,
        datafile__exposure_type='LI'  # At least header-based Light frames
    ).distinct().annotate(
        obs_date=Subquery(first_obs_date)
    ).order_by('-mid_observation_jd')[:100]

    runs = [{'id': r.id, 'name': r.name, 'obs_date': r.obs_date or ''} for r in queryset]

    return Response({
        'results': runs
    })


@extend_schema(
    summary='Trigger plate solving for specific files',
    parameters=[],
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_trigger_plate_solve(request):
    """
    Manually trigger plate solving for specific DataFiles.
    Only accessible to admin/staff users.
    
    Body:
    {
        "file_ids": [1, 2, 3]
    }
    """
    file_ids = request.data.get('file_ids', [])
    if not file_ids or not isinstance(file_ids, list):
        return Response({"detail": "file_ids must be a non-empty list"}, status=400)
    
    try:
        files = DataFile.objects.filter(
            pk__in=file_ids,
            wcs_override=False,
            spectrograph='N',  # Exclude spectra
            spectroscopy=False  # Exclude files marked as spectroscopy
        )
        if files.count() != len(file_ids):
            return Response({"detail": "Some files not found, have wcs_override=True, or are spectra (spectrograph != 'N' OR spectroscopy=True)"}, status=400)
        
        service = PlateSolvingService()
        if not service.solvers:
            return Response({"detail": "No plate solving tools available"}, status=503)
        
        results = []
        for datafile in files:
            result = solve_and_update_datafile(datafile, service=service, save=True)
            results.append({
                'file_id': datafile.pk,
                'success': result['success'],
                'tool': result.get('tool'),
                'error': result.get('error')
            })
        
        return Response({'results': results})
    except Exception as e:
        logger.exception(f'Unexpected error in admin_trigger_plate_solve: {e}')
        return Response({'error': f'Unexpected error: {str(e)}'}, status=500)


@extend_schema(
    summary='Get plate solving statistics',
    parameters=[],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_plate_solve_stats(request):
    """
    Get plate solving statistics.
    Only accessible to admin/staff users.
    """
    try:
        # Count unsolved files (Light frames only, excluding spectra)
        queryset = DataFile.objects.filter(
            wcs_override=False,
            spectrograph='N',  # Exclude spectra
            spectroscopy=False  # Exclude files marked as spectroscopy
        )
        queryset = annotate_effective_exposure_type(queryset)
        queryset = queryset.filter(annotated_effective_exposure_type='LI')
        
        stats = queryset.aggregate(
            total_light=Count('pk'),
            solved=Count('pk', filter=Q(plate_solved=True)),
            unsolved=Count('pk', filter=Q(plate_solved=False)),
            attempted=Count('pk', filter=Q(plate_solve_attempted_at__isnull=False)),
        )
        
        return Response(stats)
    except Exception as e:
        logger.exception(f'Error getting plate solve stats: {e}')
        return Response({'error': f'Unexpected error: {str(e)}'}, status=500)


@extend_schema(
    summary='Get plate solving task enabled status',
    parameters=[],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_plate_solving_task_enabled(request):
    """Get plate solving task enabled status. Redis override takes precedence over settings."""
    from django.conf import settings
    redis_value = _plate_solving_task_enabled_get()
    enabled = redis_value if redis_value is not None else getattr(settings, 'PLATE_SOLVING_ENABLED', False)
    return Response({
        'enabled': enabled,
        'source': 'redis' if redis_value is not None else 'settings',
    })


@extend_schema(
    summary='Set plate solving task enabled status',
    parameters=[],
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_set_plate_solving_task_enabled(request):
    """Set plate solving task enabled status in Redis. Admins can toggle without restart."""
    enabled = request.data.get('enabled', False)
    if not isinstance(enabled, bool):
        return Response({'detail': 'enabled must be a boolean'}, status=400)
    success = _plate_solving_task_enabled_set(enabled)
    if success:
        return Response({'enabled': enabled, 'message': 'Plate solving task status updated'})
    return Response({'detail': 'Failed to update (Redis unavailable)'}, status=500)


@extend_schema(
    summary='List all DataFiles (admin)',
    parameters=[
        OpenApiParameter('page', int, description='Page number'),
        OpenApiParameter('limit', int, description='Page size (-1 for all)'),
        OpenApiParameter('ordering', str, description='Sort field, prefix with - for desc'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_list_all_datafiles(request):
    """
    List all DataFiles with filtering. Staff/Admin only. No run visibility restriction.
    """
    from adminops.api.filters import AdminDataFileFilter

    queryset = DataFile.objects.select_related('observation_run').all()
    filterset = AdminDataFileFilter(request.query_params, queryset=queryset, request=request)
    queryset = filterset.qs

    # Ordering
    ordering = request.query_params.get('ordering', '-pk')
    allowed_sort = ['pk', 'datafile', 'observation_run', 'file_type', 'instrument', 'main_target',
                    'exposure_type', 'exptime', 'obs_date', 'plate_solved', 'plate_solve_attempted_at']
    if ordering.lstrip('-') in allowed_sort:
        queryset = queryset.order_by(ordering, 'pk')
    else:
        queryset = queryset.order_by('-pk', 'pk')

    paginator = DataFilesPagination()
    page = paginator.paginate_queryset(queryset, request)
    if page is not None:
        serializer = DataFileSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    serializer = DataFileSerializer(queryset, many=True, context={'request': request})
    return Response(serializer.data)


def _do_re_evaluate_datafiles(queryset):
    """
    Re-evaluate plate-solved DataFiles (WCS-based). Returns dict with evaluated, skipped, errors, total.
    """
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from django.conf import settings

    threshold_arcmin = getattr(settings, 'PLATE_SOLVING_RE_EVAL_COORD_THRESHOLD_ARCMIN', 5.0)
    evaluated = 0
    skipped = 0
    errors = 0

    for datafile in queryset:
        try:
            condition1 = (datafile.ra in (-1, None) or datafile.dec in (-1, None))
            condition2 = False
            if not condition1:
                c_header = SkyCoord(ra=datafile.ra * u.deg, dec=datafile.dec * u.deg)
                c_wcs = SkyCoord(ra=datafile.wcs_ra * u.deg, dec=datafile.wcs_dec * u.deg)
                sep_arcmin = c_header.separation(c_wcs).arcmin
                condition2 = sep_arcmin > threshold_arcmin

            if condition1 or condition2:
                if datafile.observation_run and datafile.wcs_ra is not None and datafile.wcs_dec is not None:
                    evaluate_data_file(
                        datafile,
                        datafile.observation_run,
                        skip_if_object_has_overrides=True,
                    )
                    update_observation_run_photometry_spectroscopy(datafile.observation_run)
                    for obj in datafile.object_set.all():
                        update_object_photometry_spectroscopy(obj)
                    evaluated += 1
                else:
                    skipped += 1
            else:
                skipped += 1
            DataFile.objects.filter(pk=datafile.pk).update(re_evaluated_after_plate_solve=True)
        except Exception as e:
            errors += 1
            logger.warning('Re-evaluation failed for datafile %s: %s', datafile.pk, e)
            DataFile.objects.filter(pk=datafile.pk).update(re_evaluated_after_plate_solve=True)

    total = evaluated + skipped + errors
    return {'evaluated': evaluated, 'skipped': skipped, 'errors': errors, 'total': total}


def _do_re_evaluate_run_all(queryset):
    """
    Re-evaluate DataFiles via evaluate_data_file.
    For plate-solved files with valid wcs_ra/wcs_dec: uses WCS coordinates for object lookup.
    For other files: uses header-derived ra/dec.
    Returns dict with evaluated, skipped, errors, total.
    """
    evaluated = 0
    skipped = 0
    errors = 0

    for datafile in queryset:
        try:
            if not datafile.observation_run:
                skipped += 1
                continue
            evaluate_data_file(
                datafile,
                datafile.observation_run,
                skip_if_object_has_overrides=True,
            )
            update_observation_run_photometry_spectroscopy(datafile.observation_run)
            for obj in datafile.object_set.all():
                update_object_photometry_spectroscopy(obj)
            evaluated += 1
        except Exception as e:
            errors += 1
            logger.warning('Re-evaluation failed for datafile %s: %s', datafile.pk, e)

    total = evaluated + skipped + errors
    return {'evaluated': evaluated, 'skipped': skipped, 'errors': errors, 'total': total}


@extend_schema(
    summary='Re-evaluate selected DataFiles',
    request=serializers.Serializer,
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_re_evaluate_datafiles(request):
    """
    Run evaluate_data_file for selected DataFiles (all files, uses header-derived ra/dec).
    Body: { "ids": [1, 2, 3] }
    """
    ids = request.data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return Response({'detail': 'ids must be a non-empty list'}, status=400)

    queryset = DataFile.objects.filter(
        pk__in=ids,
    ).select_related('observation_run')

    return Response(_do_re_evaluate_run_all(queryset))


@extend_schema(
    summary='Re-evaluate all DataFiles of an Observation Run',
    tags=['Admin'],
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_re_evaluate_run(request, run_id: int):
    """
    Re-evaluate ALL DataFiles belonging to the given Observation Run.
    Independent of plate-solving: uses evaluate_data_file with header-derived ra/dec.
    Useful for testing object detection / evaluation logic changes.
    Returns { evaluated, skipped, errors, total }.
    """
    try:
        run = ObservationRun.objects.get(pk=run_id)
    except ObservationRun.DoesNotExist:
        return Response({'detail': 'Run not found'}, status=404)

    queryset = DataFile.objects.filter(
        observation_run=run,
    ).select_related('observation_run')

    return Response(_do_re_evaluate_run_all(queryset))


@extend_schema(
    summary='Link DataFiles to an Object',
    request=serializers.Serializer,
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_link_datafiles_to_object(request):
    """
    Associate selected DataFiles with an existing Object.
    Body: { "datafile_ids": [1, 2, 3], "object_id": 123 }
    """
    datafile_ids = request.data.get('datafile_ids', [])
    object_id = request.data.get('object_id')

    if not datafile_ids or not isinstance(datafile_ids, list):
        return Response({'detail': 'datafile_ids must be a non-empty list'}, status=400)
    if object_id is None:
        return Response({'detail': 'object_id is required'}, status=400)

    try:
        obj = Object.objects.get(pk=object_id)
    except Object.DoesNotExist:
        return Response({'detail': 'Object not found'}, status=404)

    datafiles = DataFile.objects.filter(pk__in=datafile_ids).select_related('observation_run')
    linked = 0
    already_linked = 0

    for datafile in datafiles:
        if obj.datafiles.filter(pk=datafile.pk).exists():
            already_linked += 1
            continue
        obj.datafiles.add(datafile)
        if datafile.observation_run and not obj.observation_run.filter(pk=datafile.observation_run.pk).exists():
            obj.observation_run.add(datafile.observation_run)
        # Update main_target so it shows in Target column (like evaluate_data_file does)
        if should_allow_auto_update(datafile, 'main_target'):
            datafile.main_target = obj.name
            datafile.save(update_fields=['main_target'])
        linked += 1

    # Update photometry/spectroscopy flags
    try:
        update_object_photometry_spectroscopy(obj)
        if obj.observation_run.exists():
            for run in obj.observation_run.all():
                update_observation_run_photometry_spectroscopy(run)
    except Exception as e:
        logger.warning('Photometry/spectroscopy update after link failed: %s', e)

    return Response({'linked': linked, 'already_linked': already_linked})


@extend_schema(
    summary='Unlink DataFiles from Objects',
    request=serializers.Serializer,
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_unlink_datafiles_from_objects(request):
    """
    Remove Object–DataFile associations for the given DataFiles.
    Body: { "datafile_ids": [1, 2, 3] }
    """
    datafile_ids = request.data.get('datafile_ids', [])

    if not datafile_ids or not isinstance(datafile_ids, list):
        return Response({'detail': 'datafile_ids must be a non-empty list'}, status=400)

    datafiles = DataFile.objects.filter(pk__in=datafile_ids).select_related('observation_run')
    unlinked = 0
    objects_updated = set()
    runs_updated = set()

    for datafile in datafiles:
        objects = list(datafile.object_set.only('pk').all())
        for obj in objects:
            obj.datafiles.remove(datafile)
            unlinked += 1
            objects_updated.add(obj.pk)
        for obj in objects:
            try:
                update_object_photometry_spectroscopy(obj)
            except Exception as e:
                logger.warning('Photometry/spectroscopy update after unlink failed for Object #%s: %s', obj.pk, e)
        for obj in objects:
            for run in obj.observation_run.only('pk'):
                try:
                    update_observation_run_photometry_spectroscopy(run)
                    runs_updated.add(run.pk)
                except Exception:
                    pass

    return Response({
        'unlinked': unlinked,
        'objects_updated': len(objects_updated),
        'runs_updated': len(runs_updated),
    })


