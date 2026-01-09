from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from ostdata.permissions import IsAdminOrSuperuser as IsAdminUser
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.conf import settings
import os
import time
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import authenticate
from django.contrib.auth import logout as django_logout
from django.views.decorators.csrf import csrf_exempt

from users.models import User
from .serializers import UserSerializer, UserAdminSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([])  # Disable SessionAuthentication to avoid CSRF on token login
@csrf_exempt
def login(request):
    """
    Login endpoint that returns a token for authentication
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Please provide both username and password'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = authenticate(username=username, password=password)
    
    if user:
        try:
            # Light-touch: sync role flags to Django groups so ACL applies consistently
            def _ensure_group(name: str, enabled: bool):
                try:
                    grp, _ = Group.objects.get_or_create(name=name)
                    if enabled:
                        user.groups.add(grp)
                    else:
                        user.groups.remove(grp)
                except Exception:
                    pass
            _ensure_group('staff', bool(user.is_staff))
            # Custom roles if present on model
            _ensure_group('supervisor', bool(getattr(user, 'is_supervisor', False)))
            _ensure_group('student', bool(getattr(user, 'is_student', False)))
        except Exception:
            pass
        token, created = Token.objects.get_or_create(user=user)
        serializer = UserSerializer(user)
        try:
            perms_all = set(user.get_all_permissions())
            acl_perms = sorted([p for p in perms_all if p.startswith('users.acl_')])
        except Exception:
            acl_perms = []
        user_payload = serializer.data
        user_payload['perms'] = acl_perms
        return Response({
            'token': token.key,
            'user': user_payload
        })
    else:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout endpoint that deletes the user's token
    """
    try:
        # Delete the token
        request.user.auth_token.delete()
        # Also call Django's logout for session cleanup
        django_logout(request)
        return Response({'message': 'Successfully logged out'})
    except Exception as e:
        return Response(
            {'error': 'Logout failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info(request):
    """
    Get current user information
    """
    serializer = UserSerializer(request.user)
    try:
        perms_all = set(request.user.get_all_permissions())
        acl_perms = sorted([p for p in perms_all if p.startswith('users.acl_')])
    except Exception:
        acl_perms = []
    data = serializer.data
    data['perms'] = acl_perms
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change user password
    """
    old_password = request.data.get('old_password')
    new_password1 = request.data.get('new_password1')
    new_password2 = request.data.get('new_password2')
    
    if not all([old_password, new_password1, new_password2]):
        return Response(
            {'error': 'Please provide all password fields'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if new_password1 != new_password2:
        return Response(
            {'error': 'New passwords do not match'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not request.user.check_password(old_password):
        return Response(
            {'error': 'Current password is incorrect'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if len(new_password1) < 8:
        return Response(
            {'error': 'New password must be at least 8 characters long'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        request.user.set_password(new_password1)
        request.user.save()
        return Response({'message': 'Password changed successfully'})
    except Exception as e:
        return Response(
            {'error': 'Failed to change password'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class UserAdminViewSet(viewsets.ModelViewSet):
    """
    Admin-only user management (list/retrieve/update/partial_update/destroy).
    Username is immutable; account creation is out-of-scope for now.
    """
    queryset = User.objects.all().order_by('username')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAdminUser]

    def _has(self, user, codename: str) -> bool:
        try:
            return bool(user.is_superuser or user.has_perm(f'users.{codename}'))
        except Exception:
            return False

    def list(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_view'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_view'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_edit_roles'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_edit_roles'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_delete'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_ldap_test(request):
    """
    Admin-only LDAP connectivity and search test.
    Input (JSON):
      - username (optional): used to fill LDAP_USER_FILTER, defaults to empty
      - filter (optional): override filter string; if given, 'username' is ignored
    Output (JSON):
      - configured, server_uri, can_import, bind_ok, errors
      - search_ok, latency_ms, count, first_dn, attrs (subset)
      - mapping_preview: { first_name, last_name, email }
      - groups: { staff, superuser, supervisor, student } (if DNs configured)
    """
    result = {
        'configured': False,
        'server_uri': None,
        'can_import': False,
        'bind_ok': False,
        'search_ok': False,
        'errors': {},
        'count': 0,
        'first_dn': None,
        'attrs': {},
        'mapping_preview': {},
        'groups': {},
    }
    server_uri = getattr(settings, 'AUTH_LDAP_SERVER_URI', None) or os.environ.get('LDAP_SERVER_URI')
    if not server_uri:
        return Response(result)
    result['configured'] = True
    result['server_uri'] = server_uri

    try:
        import ldap  # type: ignore
        result['can_import'] = True
    except Exception as e:
        result['errors']['import'] = str(e)
        return Response(result)

    start_tls = bool(getattr(settings, 'AUTH_LDAP_START_TLS', False) or str(os.environ.get('LDAP_START_TLS', 'false')).lower() in ('1', 'true', 'yes'))
    bind_dn = getattr(settings, 'AUTH_LDAP_BIND_DN', None) or os.environ.get('LDAP_BIND_DN') or ''
    bind_pw = getattr(settings, 'AUTH_LDAP_BIND_PASSWORD', None) or os.environ.get('LDAP_BIND_PASSWORD') or ''
    search_base = os.environ.get('LDAP_USER_SEARCH_BASE') or getattr(settings, 'LDAP_USER_SEARCH_BASE', None) or ''
    user_filter_tpl = os.environ.get('LDAP_USER_FILTER') or getattr(settings, 'LDAP_USER_FILTER', '(uid=%(user)s)')

    username = (request.data or {}).get('username') or ''
    override_filter = (request.data or {}).get('filter') or ''
    search_filter = override_filter or (user_filter_tpl.replace('%(user)s', username) if username else user_filter_tpl)

    try:
        conn = ldap.initialize(server_uri)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        if start_tls:
            try:
                conn.start_tls_s()
            except Exception as e:
                result['errors']['start_tls'] = str(e)
        try:
            if bind_dn:
                conn.simple_bind_s(bind_dn, bind_pw or '')
            else:
                conn.simple_bind_s()
            result['bind_ok'] = True
        except Exception as e:
            result['errors']['bind'] = str(e)
            try:
                conn.unbind_s()
            except Exception:
                pass
            return Response(result)

        # Perform search
        try:
            t0 = time.time()
            scope = ldap.SCOPE_SUBTREE
            attrs = ['uid', 'mail', 'givenName', 'sn', 'cn', 'memberOf']
            entries = conn.search_s(search_base, scope, search_filter, attrs)
            latency_ms = int((time.time() - t0) * 1000)
            result['search_ok'] = True
            result['latency_ms'] = latency_ms
            result['count'] = len(entries)
            # Extract first entry
            if entries:
                dn, vals = entries[0]
                result['first_dn'] = dn
                # Convert bytes to strings where needed
                def _first_str(vlist):
                    if not isinstance(vlist, (list, tuple)) or not vlist:
                        return ''
                    v = vlist[0]
                    try:
                        return v.decode('utf-8') if isinstance(v, (bytes, bytearray)) else str(v)
                    except Exception:
                        return str(v)
                result['attrs'] = {
                    'uid': _first_str(vals.get('uid', [])),
                    'mail': _first_str(vals.get('mail', [])),
                    'givenName': _first_str(vals.get('givenName', [])),
                    'sn': _first_str(vals.get('sn', [])),
                    'cn': _first_str(vals.get('cn', [])),
                }
                result['mapping_preview'] = {
                    'first_name': result['attrs'].get('givenName') or '',
                    'last_name': result['attrs'].get('sn') or '',
                    'email': result['attrs'].get('mail') or '',
                }
                # Group membership based on configured group DNs; prefer memberOf, fallback to memberUid
                member_of = []
                try:
                    member_of = [ (x.decode('utf-8') if isinstance(x, (bytes, bytearray)) else str(x)) for x in (vals.get('memberOf', []) or []) ]
                except Exception:
                    member_of = []
                
                # Get user UID for memberUid checks
                user_uid = result['attrs'].get('uid', '')
                
                def _check_group_via_memberuid(group_dn, uid):
                    """Helper function to check group membership via memberUid"""
                    if not group_dn or not uid:
                        return False
                    try:
                        attrs = ['memberUid']
                        group_result = conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=*)', attrs)
                        if group_result:
                            _, group_vals = group_result[0]
                            member_uids = group_vals.get('memberUid', [])
                            if member_uids:
                                member_uids_str = []
                                for muid in member_uids:
                                    try:
                                        muid_str = muid.decode('utf-8') if isinstance(muid, (bytes, bytearray)) else str(muid)
                                        member_uids_str.append(muid_str)
                                    except Exception:
                                        member_uids_str.append(str(muid))
                                return uid in member_uids_str
                    except Exception:
                        pass
                    return False
                
                grp = {}
                staff_dn = getattr(settings, 'AUTH_LDAP_IS_STAFF_MEMBER', None) or os.environ.get('LDAP_GROUP_STAFF_DN')
                superuser_dn = getattr(settings, 'AUTH_LDAP_IS_SUPERUSER_MEMBER', None) or os.environ.get('LDAP_GROUP_SUPERUSER_DN')
                supervisor_dn = getattr(settings, 'AUTH_LDAP_IS_SUPERVISOR_MEMBER', None) or os.environ.get('LDAP_GROUP_SUPERVISOR_DN')
                student_dn = getattr(settings, 'AUTH_LDAP_IS_STUDENT_MEMBER', None) or os.environ.get('LDAP_GROUP_STUDENT_DN')
                
                if staff_dn:
                    # First check memberOf
                    grp['staff'] = any(staff_dn.lower() == mo.lower() for mo in member_of)
                    # If not found, try memberUid
                    if not grp['staff'] and user_uid:
                        grp['staff'] = _check_group_via_memberuid(staff_dn, user_uid)
                if superuser_dn:
                    # First check memberOf
                    grp['superuser'] = any(superuser_dn.lower() == mo.lower() for mo in member_of)
                    # If not found, try memberUid
                    if not grp['superuser'] and user_uid:
                        grp['superuser'] = _check_group_via_memberuid(superuser_dn, user_uid)
                if supervisor_dn:
                    # First check memberOf
                    grp['supervisor'] = any(supervisor_dn.lower() == mo.lower() for mo in member_of)
                    # If not found, try memberUid
                    if not grp['supervisor'] and user_uid:
                        grp['supervisor'] = _check_group_via_memberuid(supervisor_dn, user_uid)
                if student_dn:
                    # First check memberOf
                    grp['student'] = any(student_dn.lower() == mo.lower() for mo in member_of)
                    # If not found, try memberUid
                    if not grp['student'] and user_uid:
                        grp['student'] = _check_group_via_memberuid(student_dn, user_uid)
                result['groups'] = grp
        except Exception as e:
            result['errors']['search'] = str(e)
        finally:
            try:
                conn.unbind_s()
            except Exception:
                pass
    except Exception as e:
        result['errors']['connect'] = str(e)

    return Response(result)


# =========================
# ACL management (groups/permissions)
# =========================

ACL_PERMISSIONS = [
    # (codename, name)
    ('acl_users_view', 'Users: view'),
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
]

ACL_GROUPS = ['staff', 'supervisor', 'student']

ACL_DEFAULTS = {
    'staff': {
        'acl_users_view', 'acl_objects_view_private', 'acl_objects_edit', 'acl_objects_merge',
        'acl_runs_edit', 'acl_runs_publish', 'acl_tags_manage', 'acl_jobs_view_all',
        'acl_jobs_cancel_any', 'acl_jobs_ttl_modify', 'acl_maintenance_cleanup',
        'acl_maintenance_reconcile', 'acl_maintenance_orphans', 'acl_banner_manage',
        'acl_system_health_view', 'acl_system_settings_view',
    },
    'supervisor': {
        'acl_users_view', 'acl_objects_view_private', 'acl_objects_edit', 'acl_objects_merge',
        'acl_runs_edit', 'acl_runs_publish', 'acl_tags_manage', 'acl_jobs_view_all',
        'acl_system_health_view',
    },
    'student': {
        'acl_users_view', 'acl_system_health_view',
    },
}

def _acl_bootstrap():
    """
    Ensure permissions and groups exist and defaults are present.
    """
    # Attach custom permissions to the User content type for simplicity
    ct = ContentType.objects.get_for_model(User)
    existing = {p.codename: p for p in Permission.objects.filter(content_type=ct, codename__in=[c for c, _ in ACL_PERMISSIONS])}
    for codename, name in ACL_PERMISSIONS:
        if codename not in existing:
            Permission.objects.get_or_create(codename=codename, content_type=ct, defaults={'name': name})
    # Ensure groups
    for g in ACL_GROUPS:
        Group.objects.get_or_create(name=g)
    # Apply defaults only if the group currently has no of our ACL permissions
    for gname, perm_set in ACL_DEFAULTS.items():
        try:
            grp = Group.objects.get(name=gname)
        except Group.DoesNotExist:
            continue
        current = set(grp.permissions.filter(content_type=ct, codename__in=[c for c, _ in ACL_PERMISSIONS]).values_list('codename', flat=True))
        if not current:
            perms = list(Permission.objects.filter(content_type=ct, codename__in=list(perm_set)))
            grp.permissions.add(*perms)

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_acl_get(request):
    """
    Return ACL matrix: groups, permissions, and which groups have which perms.
    """
    _acl_bootstrap()
    ct = ContentType.objects.get_for_model(User)
    perms = list(Permission.objects.filter(content_type=ct, codename__in=[c for c, _ in ACL_PERMISSIONS]).order_by('codename'))
    groups = list(Group.objects.filter(name__in=ACL_GROUPS).order_by('name'))
    matrix = {}
    for g in groups:
        matrix[g.name] = set(g.permissions.filter(id__in=[p.id for p in perms]).values_list('codename', flat=True))
    payload = {
        'groups': [g.name for g in groups],
        'permissions': [{'codename': p.codename, 'name': p.name} for p in perms],
        'matrix': { g: list(codes) for g, codes in matrix.items() },
        'defaults': { k: list(v) for k, v in ACL_DEFAULTS.items() },
    }
    return Response(payload)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_acl_set(request):
    """
    Set ACL matrix. Body: { matrix: { group: [codenames...] } }
    Only affects known groups and known ACL permissions.
    """
    _acl_bootstrap()
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
    return admin_acl_get(request)
    