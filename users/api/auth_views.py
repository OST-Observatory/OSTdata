import logging

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.models import Group
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .serializers import UserSerializer

logger = logging.getLogger(__name__)


def _user_payload(user):
    serializer = UserSerializer(user)
    try:
        perms_all = set(user.get_all_permissions())
        acl_perms = sorted([p for p in perms_all if p.startswith('users.acl_')])
    except Exception:
        logger.warning('Failed to load ACL permissions for %s', user.username, exc_info=True)
        acl_perms = []
    data = serializer.data
    data['perms'] = acl_perms
    return data


def _sync_role_groups(user):
    def _ensure_group(name: str, enabled: bool):
        try:
            grp, _ = Group.objects.get_or_create(name=name)
            if enabled:
                user.groups.add(grp)
            else:
                user.groups.remove(grp)
        except Exception:
            logger.warning('Failed to sync group %s for user %s', name, user.username, exc_info=True)

    try:
        _ensure_group('staff', bool(user.is_staff))
        _ensure_group('supervisor', bool(getattr(user, 'is_supervisor', False)))
        _ensure_group('student', bool(getattr(user, 'is_student', False)))
    except Exception:
        logger.warning('Group sync failed during login for %s', user.username, exc_info=True)


@api_view(['GET'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf_cookie(request):
    """Set CSRF cookie for SPA clients before login or unsafe API calls."""
    return Response({'authenticated': bool(request.user.is_authenticated)})


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Session login: establishes Django session cookie (HttpOnly).
    Requires valid CSRF token (X-CSRFToken header) from prior GET /auth/csrf/.
    """
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response(
            {'error': 'Please provide both username and password'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request=request, username=username, password=password)

    if not user:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    django_login(request, user)
    _sync_role_groups(user)
    return Response({'user': _user_payload(user)})


login.throttle_classes = [ScopedRateThrottle]
login.throttle_scope = 'login'


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """End the current session."""
    try:
        django_logout(request)
        return Response({'message': 'Successfully logged out'})
    except Exception:
        logger.warning('Logout failed for user %s', getattr(request.user, 'username', '?'), exc_info=True)
        return Response(
            {'error': 'Logout failed'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info(request):
    """Get current user information from session."""
    return Response(_user_payload(request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """Change password and invalidate the current session (re-login required)."""
    old_password = request.data.get('old_password')
    new_password1 = request.data.get('new_password1')
    new_password2 = request.data.get('new_password2')

    if not all([old_password, new_password1, new_password2]):
        return Response(
            {'error': 'Please provide all password fields'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if new_password1 != new_password2:
        return Response(
            {'error': 'New passwords do not match'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not request.user.check_password(old_password):
        return Response(
            {'error': 'Current password is incorrect'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if len(new_password1) < 8:
        return Response(
            {'error': 'New password must be at least 8 characters long'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        request.user.set_password(new_password1)
        request.user.save()
        django_logout(request)
        return Response({
            'message': 'Password changed successfully. Please log in again.',
            'relogin_required': True,
        })
    except Exception:
        logger.warning('Password change failed for %s', request.user.username, exc_info=True)
        return Response(
            {'error': 'Failed to change password'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
