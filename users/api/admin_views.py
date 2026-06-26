import logging

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User
from .serializers import UserAdminSerializer

logger = logging.getLogger(__name__)



class UserAdminViewSet(viewsets.ModelViewSet):
    """
    Admin-only user management (list/retrieve/update/partial_update/destroy).
    Username is immutable; account creation is out-of-scope for now.
    """
    queryset = User.objects.all().order_by('username')
    serializer_class = UserAdminSerializer
    permission_classes = [IsAuthenticated]

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

    _AUDIT_USER_FIELDS = (
        'is_active', 'is_staff', 'is_supervisor', 'is_student',
        'email', 'first_name', 'last_name', 'note',
    )

    def _audit_log_user_changes(self, instance, request, changes: list):
        if not changes:
            return
        try:
            from adminops.audit_events import log_audit_event
            log_audit_event(
                model_type='user_role',
                action='updated',
                entity_label=instance.username,
                entity_path='/admin/users',
                change_reason='admin:user_roles',
                user=request.user,
                instance_id=instance.pk,
                changes=changes,
                summary=f'Updated user {instance.username}',
            )
        except Exception:
            logger.warning('Audit log failed for user update', exc_info=True)

    def perform_update(self, serializer):
        instance = serializer.instance
        old_values = {
            field: getattr(instance, field)
            for field in self._AUDIT_USER_FIELDS
            if field in serializer.validated_data
        }
        serializer.save()
        changes = []
        for field, old_val in old_values.items():
            new_val = getattr(serializer.instance, field)
            if old_val != new_val:
                changes.append({'field': field, 'old': old_val, 'new': new_val})
        self._audit_log_user_changes(serializer.instance, self.request, changes)

    def perform_destroy(self, instance):
        try:
            from adminops.audit_events import log_audit_event
            log_audit_event(
                model_type='user_role',
                action='deleted',
                entity_label=instance.username,
                entity_path='/admin/users',
                change_reason='admin:user_delete',
                user=self.request.user,
                instance_id=instance.pk,
                summary=f'User {instance.username} deleted',
            )
        except Exception:
            logger.warning('Audit log failed for user delete', exc_info=True)
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        if not self._has(request.user, 'acl_users_delete'):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)


