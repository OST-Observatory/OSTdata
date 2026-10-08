import logging
import os
import time

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ostdata.openapi import JSON_OBJECT_RESPONSE, EmptyObjectSerializer
from ostdata.permissions import HasPerm
from users.ldap_membership import ldap_group_membership

logger = logging.getLogger(__name__)

@extend_schema(summary='Admin LDAP connectivity test', tags=['Admin'], responses=JSON_OBJECT_RESPONSE,
    request=EmptyObjectSerializer)
@api_view(['POST'])
@permission_classes([IsAuthenticated, HasPerm('acl_users_view')])
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
    # Free-form filter overrides are not allowed (LDAP injection risk).
    if (request.data or {}).get('filter'):
        return Response({'detail': 'Custom LDAP filters are not allowed'}, status=400)
    try:
        from ldap.filter import escape_filter_chars  # type: ignore
        safe_username = escape_filter_chars(str(username)) if username else ''
    except Exception:
        # Conservative fallback: strip LDAP filter metacharacters
        safe_username = ''.join(c for c in str(username) if c.isalnum() or c in '._-@')
    if not safe_username:
        return Response({'detail': 'username is required'}, status=400)
    search_filter = user_filter_tpl.replace('%(user)s', safe_username)

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
            # Cap returned entries to avoid dumping large directories
            entries = (entries or [])[:25]
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
                
                # Same membership check as used at login (users.ldap_setup)
                user_uid = result['attrs'].get('uid', '')
                grp = {}
                grp_via = {}
                group_specs = (
                    ('staff', getattr(settings, 'LDAP_GROUP_STAFF_DN', None) or os.environ.get('LDAP_GROUP_STAFF_DN')),
                    ('superuser', getattr(settings, 'LDAP_GROUP_SUPERUSER_DN', None) or os.environ.get('LDAP_GROUP_SUPERUSER_DN')),
                    ('supervisor', getattr(settings, 'LDAP_GROUP_SUPERVISOR_DN', None) or os.environ.get('LDAP_GROUP_SUPERVISOR_DN')),
                    ('student', getattr(settings, 'LDAP_GROUP_STUDENT_DN', None) or os.environ.get('LDAP_GROUP_STUDENT_DN')),
                )
                for key, group_dn in group_specs:
                    if not group_dn:
                        continue
                    method = ldap_group_membership(
                        conn, group_dn, user_dn=dn, user_uid=user_uid, known_group_dns=member_of,
                    )
                    grp[key] = bool(method)
                    grp_via[key] = method or None
                result['groups'] = grp
                result['groups_via'] = grp_via
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
