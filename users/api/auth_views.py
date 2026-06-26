import logging

from django.contrib.auth import authenticate, logout as django_logout
from django.contrib.auth.models import Group, update_last_login
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from users.models import User
from .serializers import UserSerializer

logger = logging.getLogger(__name__)


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
        # Token login bypasses django.contrib.auth.login(); update last_login explicitly.
        update_last_login(None, user)
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
                    logger.warning('Failed to sync group %s for user %s', name, user.username, exc_info=True)
            _ensure_group('staff', bool(user.is_staff))
            # Custom roles if present on model
            _ensure_group('supervisor', bool(getattr(user, 'is_supervisor', False)))
            _ensure_group('student', bool(getattr(user, 'is_student', False)))
        except Exception:
            logger.warning('Group sync failed during login for %s', user.username, exc_info=True)
        token, created = Token.objects.get_or_create(user=user)
        serializer = UserSerializer(user)
        try:
            perms_all = set(user.get_all_permissions())
            acl_perms = sorted([p for p in perms_all if p.startswith('users.acl_')])
        except Exception:
            logger.warning('Failed to load ACL permissions for %s', user.username, exc_info=True)
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
        logger.warning('Failed to load ACL permissions for %s', request.user.username, exc_info=True)
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
