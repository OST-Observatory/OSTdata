from rest_framework.permissions import BasePermission


class HasPerm(BasePermission):
    """
    Generic permission that checks for a Django permission codename on the 'users' app.
    Example: HasPerm('acl_runs_edit') checks user.has_perm('users.acl_runs_edit') or is_superuser.
    """
    perm_codename: str = ''

    def __init__(self, perm_codename: str = ''):
        if perm_codename:
            self.perm_codename = perm_codename

    def has_permission(self, request, view):
        try:
            if getattr(request.user, 'is_superuser', False):
                return True
            if not self.perm_codename:
                return False
            return request.user.has_perm(f'users.{self.perm_codename}')
        except Exception:
            return False


class IsAdminOrSuperuser(BasePermission):
    """
    Permission class that allows access if user is staff OR superuser.
    This fixes the issue where LDAP users with is_superuser=True but is_staff=False
    cannot access admin endpoints that use IsAdminUser (which only checks is_staff).
    """
    def has_permission(self, request, view):
        try:
            user = request.user
            if not user or not user.is_authenticated:
                return False
            # Allow if user is staff OR superuser
            return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
        except Exception:
            return False

