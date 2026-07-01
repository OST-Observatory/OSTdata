import logging

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ostdata.permissions import HasPerm
from users.models import User

logger = logging.getLogger(__name__)

# =========================
# ACL management (groups/permissions)
# =========================

ACL_PERMISSIONS = [
    # (codename, name)
    ('acl_users_view', 'Users: view'),
    ('acl_admin_audit_log_view', 'Admin: audit log view'),
    ('acl_users_edit_roles', 'Users: edit roles'),
    ('acl_users_delete', 'Users: delete'),
    ('acl_objects_view_private', 'Objects: view private'),
    ('acl_objects_edit', 'Objects: edit'),
    ('acl_objects_merge', 'Objects: merge'),
    ('acl_objects_delete', 'Objects: delete'),
    ('acl_runs_edit', 'Runs: edit'),
    ('acl_runs_delete', 'Runs: delete'),
    ('acl_runs_publish', 'Runs: publish/unpublish'),
    ('acl_tags_manage', 'Tags: manage'),
    ('acl_jobs_view_all', 'Jobs: view all'),
    ('acl_jobs_cancel_any', 'Jobs: cancel any'),
    ('acl_jobs_ttl_modify', 'Jobs: modify TTL'),
    ('acl_maintenance_cleanup', 'Maintenance: cleanup'),
    ('acl_maintenance_reconcile', 'Maintenance: reconcile'),
    ('acl_maintenance_orphans', 'Maintenance: orphans/hashcheck'),
    ('acl_banner_manage', 'Banner: manage'),
    ('acl_system_health_view', 'System: health view'),
    ('acl_system_settings_view', 'System: settings view'),
    # Data file tools (admin/bulk)
    ('acl_datafiles_plate_solve', 'Data files: plate solve'),
    ('acl_datafiles_reevaluate', 'Data files: re-evaluate'),
    ('acl_datafiles_clear_overrides', 'Data files: clear overrides'),
    ('acl_datafiles_exposure_type_user', 'Data files: set user exposure type'),
    ('acl_datafiles_spectrograph', 'Data files: set spectrograph'),
    ('acl_datafiles_link_object', 'Data files: link to object'),
    ('acl_datafiles_unlink_object', 'Data files: unlink from objects'),
    ('acl_run_datafiles_bulk_admin', 'Runs: re-evaluate all datafiles'),
    ('acl_runs_aux_objects_admin', 'Runs: auxiliary SIMBAD objects (admin)'),
    # Observation run detail page
    ('acl_run_detail_clear_overrides', 'Runs Detail: clear run override flags'),
    ('acl_run_detail_edit_obs_type', 'Runs Detail: edit observation type'),
    ('acl_run_detail_edit_notes', 'Runs Detail: edit notes'),
    ('acl_run_detail_edit_tags', 'Runs Detail: edit tags'),
    # Object detail page tools
    ('acl_object_detail_edit_basic', 'Objects Detail: edit basic data'),
    ('acl_object_detail_edit_notes', 'Objects Detail: edit notes'),
    ('acl_object_detail_edit_tags', 'Objects Detail: edit tags'),
    ('acl_object_simbad_reanalyze', 'Objects Detail: SIMBAD re-analyse'),
    ('acl_object_admin_edit', 'Objects Detail: admin edit'),
    ('acl_object_simbad_identifiers', 'Objects Detail: SIMBAD update identifiers'),
    ('acl_object_delete_aliases', 'Objects Detail: delete all aliases'),
]

ACL_GROUPS = ['staff', 'supervisor', 'student']

_NEW_STAFF_DATAFILE_TOOLS = {
    'acl_datafiles_plate_solve', 'acl_datafiles_reevaluate', 'acl_datafiles_clear_overrides',
    'acl_datafiles_exposure_type_user', 'acl_datafiles_spectrograph', 'acl_datafiles_link_object',
    'acl_datafiles_unlink_object', 'acl_run_datafiles_bulk_admin',
    'acl_runs_aux_objects_admin',
    'acl_run_detail_clear_overrides', 'acl_run_detail_edit_obs_type',
    'acl_run_detail_edit_notes', 'acl_run_detail_edit_tags',
    'acl_object_detail_edit_basic', 'acl_object_detail_edit_notes', 'acl_object_detail_edit_tags',
    'acl_object_simbad_reanalyze', 'acl_object_admin_edit', 'acl_object_simbad_identifiers',
    'acl_object_delete_aliases',
}

ACL_DEFAULTS = {
    'staff': {
        'acl_users_view', 'acl_objects_view_private', 'acl_objects_edit', 'acl_objects_merge',
        'acl_objects_delete', 'acl_runs_edit', 'acl_runs_delete', 'acl_runs_publish', 'acl_tags_manage',
        'acl_jobs_view_all', 'acl_jobs_cancel_any', 'acl_jobs_ttl_modify', 'acl_maintenance_cleanup',
        'acl_maintenance_reconcile', 'acl_maintenance_orphans', 'acl_banner_manage',
        'acl_system_health_view', 'acl_system_settings_view', 'acl_admin_audit_log_view',
    } | _NEW_STAFF_DATAFILE_TOOLS,
    'supervisor': {
        'acl_users_view', 'acl_admin_audit_log_view', 'acl_objects_view_private', 'acl_objects_edit', 'acl_objects_merge',
        'acl_runs_edit', 'acl_runs_publish', 'acl_tags_manage', 'acl_jobs_view_all',
        'acl_system_health_view',
    },
    'student': {
        'acl_users_view', 'acl_system_health_view',
    },
}

def _ensure_acl_registry():
    """
    Create ACL permission rows and role groups if missing.
    Does not assign permissions to groups (safe to call on every API read/write).
    """
    ct = ContentType.objects.get_for_model(User)
    existing = {p.codename: p for p in Permission.objects.filter(content_type=ct, codename__in=[c for c, _ in ACL_PERMISSIONS])}
    for codename, name in ACL_PERMISSIONS:
        perm, created = Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={'name': name},
        )
        if not created and perm.name != name:
            perm.name = name
            perm.save(update_fields=['name'])
    for g in ACL_GROUPS:
        Group.objects.get_or_create(name=g)


def _apply_acl_group_defaults_if_empty():
    """
    Apply ACL_DEFAULTS to groups that have no ACL permissions yet (first-time setup only).
    Not used on normal API GET/SET — otherwise saving an empty matrix would be reverted.
    """
    ct = ContentType.objects.get_for_model(User)
    codenames = [c for c, _ in ACL_PERMISSIONS]
    for gname, perm_set in ACL_DEFAULTS.items():
        try:
            grp = Group.objects.get(name=gname)
        except Group.DoesNotExist:
            continue
        current = set(
            grp.permissions.filter(content_type=ct, codename__in=codenames).values_list('codename', flat=True)
        )
        if not current:
            perms = list(Permission.objects.filter(content_type=ct, codename__in=list(perm_set)))
            if perms:
                grp.permissions.add(*perms)


def _acl_bootstrap():
    """
    Full bootstrap for management commands / upgrades: registry, empty-group defaults, staff sync.
    """
    _ensure_acl_registry()
    _apply_acl_group_defaults_if_empty()
    _sync_missing_acl_to_staff()


def _sync_missing_acl_to_staff():
    """Add any ACL_DEFAULTS['staff'] permissions missing from the staff group (non-destructive)."""
    ct = ContentType.objects.get_for_model(User)
    desired = ACL_DEFAULTS.get('staff', set())
    try:
        grp = Group.objects.get(name='staff')
    except Group.DoesNotExist:
        return
    existing = set(
        grp.permissions.filter(
            content_type=ct,
            codename__in=[c for c, _ in ACL_PERMISSIONS],
        ).values_list('codename', flat=True)
    )
    missing = desired - existing
    if missing:
        perms = list(Permission.objects.filter(content_type=ct, codename__in=list(missing)))
        if perms:
            grp.permissions.add(*perms)


def _build_acl_payload():
    """Build ACL matrix dict (groups, permissions, matrix, defaults)."""
    _ensure_acl_registry()
    _sync_missing_acl_to_staff()
    ct = ContentType.objects.get_for_model(User)
    perms = list(
        Permission.objects.filter(
            content_type=ct,
            codename__in=[c for c, _ in ACL_PERMISSIONS],
        ).order_by('codename')
    )
    groups = list(Group.objects.filter(name__in=ACL_GROUPS).order_by('name'))
    perm_ids = [p.id for p in perms]
    matrix = {}
    for g in groups:
        matrix[g.name] = list(
            g.permissions.filter(id__in=perm_ids).values_list('codename', flat=True)
        )
    return {
        'groups': [g.name for g in groups],
        'permissions': [{'codename': p.codename, 'name': p.name} for p in perms],
        'matrix': matrix,
        'defaults': {k: list(v) for k, v in ACL_DEFAULTS.items()},
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated, HasPerm('acl_users_view')])
def admin_acl_get(request):
    """
    Return ACL matrix: groups, permissions, and which groups have which perms.
    """
    return Response(_build_acl_payload())

@api_view(['POST'])
@permission_classes([IsAuthenticated, HasPerm('acl_users_edit_roles')])
def admin_acl_set(request):
    """
    Set ACL matrix. Body: { matrix: { group: [codenames...] } }
    Only affects known groups and known ACL permissions.
    """
    _ensure_acl_registry()
    body = request.data or {}
    new_matrix = body.get('matrix') or {}
    ct = ContentType.objects.get_for_model(User)
    valid_perms = {c for c, _ in ACL_PERMISSIONS}
    perm_map = {p.codename: p.id for p in Permission.objects.filter(content_type=ct, codename__in=valid_perms)}
    for gname, codes in (new_matrix.items() if isinstance(new_matrix, dict) else []):
        if gname not in ACL_GROUPS:
            continue
        try:
            grp = Group.objects.get(name=gname)
        except Group.DoesNotExist:
            continue
        codes = [c for c in (codes or []) if c in perm_map]
        # Replace group's ACL permissions atomically: remove old ACL perms, add selected
        current_qs = grp.permissions.filter(content_type=ct, codename__in=list(valid_perms))
        grp.permissions.remove(*list(current_qs))
        if codes:
            to_add = list(Permission.objects.filter(id__in=[perm_map[c] for c in codes]))
            grp.permissions.add(*to_add)
    try:
        from adminops.audit_events import log_audit_event
        log_audit_event(
            model_type='acl',
            action='updated',
            entity_label='ACL role matrix',
            entity_path='/admin/users',
            change_reason='admin:acl_set',
            user=request.user,
            changes=[{'field': 'matrix', 'old': None, 'new': new_matrix}],
            summary='ACL permissions updated for role groups',
        )
    except Exception:
        pass
    return Response(_build_acl_payload())
    