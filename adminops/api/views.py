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
)
from ostdata.services.health import gather_admin_health
from obs_run.models import ObservationRun, DataFile
from obs_run.api.serializers import DataFileSerializer
from obs_run.api.views import DataFilesPagination
from objects.models import Object, Identifier
from utilities import _query_object_variants, _query_region_safe, update_observation_run_photometry_spectroscopy, update_object_photometry_spectroscopy
from django.db.models import Q, F


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
    summary='Get exposure type discrepancies',
    parameters=[
        OpenApiParameter('header_type', str, OpenApiParameter.QUERY, description='Filter by header exposure type'),
        OpenApiParameter('ml_type', str, OpenApiParameter.QUERY, description='Filter by ML exposure type'),
        OpenApiParameter('observation_run', int, OpenApiParameter.QUERY, description='Filter by observation run ID'),
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

    # Filter by observation_run
    observation_run_id = request.query_params.get('observation_run')
    if observation_run_id:
        try:
            queryset = queryset.filter(observation_run_id=int(observation_run_id))
        except ValueError:
            pass

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

    serializer = DataFileSerializer(datafile)
    return Response(serializer.data)


@extend_schema(
    summary='Get DataFiles for spectrograph management',
    parameters=[
        OpenApiParameter('spectrograph', str, OpenApiParameter.QUERY, description='Filter by spectrograph type'),
        OpenApiParameter('exposure_type', str, OpenApiParameter.QUERY, description='Filter by exposure type'),
        OpenApiParameter('observation_run', int, OpenApiParameter.QUERY, description='Filter by observation run ID'),
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

    # Filter by observation_run
    observation_run_id = request.query_params.get('observation_run')
    if observation_run_id:
        try:
            queryset = queryset.filter(observation_run_id=int(observation_run_id))
        except ValueError:
            pass

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


