from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.conf import settings
import os
import time
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
        token, created = Token.objects.get_or_create(user=user)
        serializer = UserSerializer(user)
        return Response({
            'token': token.key,
            'user': serializer.data
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
    return Response(serializer.data)


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
                # Group membership based on configured group DNs; prefer memberOf
                member_of = []
                try:
                    member_of = [ (x.decode('utf-8') if isinstance(x, (bytes, bytearray)) else str(x)) for x in (vals.get('memberOf', []) or []) ]
                except Exception:
                    member_of = []
                grp = {}
                staff_dn = getattr(settings, 'AUTH_LDAP_IS_STAFF_MEMBER', None) or os.environ.get('LDAP_GROUP_STAFF_DN')
                superuser_dn = getattr(settings, 'AUTH_LDAP_IS_SUPERUSER_MEMBER', None) or os.environ.get('LDAP_GROUP_SUPERUSER_DN')
                supervisor_dn = getattr(settings, 'AUTH_LDAP_IS_SUPERVISOR_MEMBER', None) or os.environ.get('LDAP_GROUP_SUPERVISOR_DN')
                student_dn = getattr(settings, 'AUTH_LDAP_IS_STUDENT_MEMBER', None) or os.environ.get('LDAP_GROUP_STUDENT_DN')
                if staff_dn:
                    grp['staff'] = any(staff_dn.lower() == mo.lower() for mo in member_of)
                if superuser_dn:
                    grp['superuser'] = any(superuser_dn.lower() == mo.lower() for mo in member_of)
                if supervisor_dn:
                    grp['supervisor'] = any(supervisor_dn.lower() == mo.lower() for mo in member_of)
                if student_dn:
                    grp['student'] = any(student_dn.lower() == mo.lower() for mo in member_of)
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