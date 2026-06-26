import logging
import os
import time

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ostdata.permissions import HasPerm

logger = logging.getLogger(__name__)

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
