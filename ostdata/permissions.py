from rest_framework.permissions import BasePermission, IsAuthenticated


def HasPerm(perm_codename: str):
    """
    Factory returning a DRF permission class for a users.acl_* codename.
    Usage: @permission_classes([IsAuthenticated, HasPerm('acl_users_view')])
    DRF instantiates the returned class with (), so this must be a factory, not an instance.
    """
    codename = perm_codename

    class _HasPerm(BasePermission):
        def has_permission(self, request, view):
            return user_has_acl(request.user, codename)

    _HasPerm.__name__ = f'HasPerm_{codename}'
    _HasPerm.__qualname__ = f'HasPerm_{codename}'
    return _HasPerm


def user_has_acl(user, codename: str) -> bool:
    try:
        if getattr(user, 'is_superuser', False):
            return True
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return user.has_perm(f'users.{codename}')
    except Exception:
        return False


def IsAuthenticatedWithAcl(codename: str):
    """Factory: IsAuthenticated + ACL check (superuser bypasses)."""
    acl_codename = codename

    class _IsAuthenticatedWithAcl(BasePermission):
        def has_permission(self, request, view):
            if not IsAuthenticated().has_permission(request, view):
                return False
            return user_has_acl(request.user, acl_codename)

    _IsAuthenticatedWithAcl.__name__ = f'IsAuthenticatedWithAcl_{acl_codename}'
    return _IsAuthenticatedWithAcl


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
            return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))
        except Exception:
            return False
