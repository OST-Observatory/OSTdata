"""LDAP configuration extracted from Django settings."""
import logging

logger = logging.getLogger(__name__)


def configure_ldap_from_env(g, env):
    """Apply LDAP auth backend settings when AUTH_LDAP_SERVER_URI is configured."""
    server_uri = g.get('AUTH_LDAP_SERVER_URI') or ''
    if not server_uri:
        return

    connect_timeout = g.get('AUTH_LDAP_CONNECT_TIMEOUT', 5)
    user_search_base = g.get('AUTH_LDAP_USER_SEARCH_BASE', '')
    group_search_base = g.get('AUTH_LDAP_GROUP_SEARCH_BASE', '')
    user_filter = g.get('AUTH_LDAP_USER_FILTER', '(uid=%(user)s)')
    staff_dn = g.get('LDAP_GROUP_STAFF_DN', '')
    superuser_dn = g.get('LDAP_GROUP_SUPERUSER_DN', '')
    supervisor_dn = g.get('LDAP_GROUP_SUPERVISOR_DN', '')
    student_dn = g.get('LDAP_GROUP_STUDENT_DN', '')

    try:
        import ldap  # type: ignore
        from django_auth_ldap.config import GroupOfNamesType, LDAPSearch

        g['AUTHENTICATION_BACKENDS'] = (
            'django_auth_ldap.backend.LDAPBackend',
            'django.contrib.auth.backends.ModelBackend',
        )
        g['AUTH_LDAP_CONNECTION_OPTIONS'] = {
            getattr(ldap, 'OPT_NETWORK_TIMEOUT'): connect_timeout,
        }
        g['AUTH_LDAP_ALWAYS_UPDATE_USER'] = True
        g['AUTH_LDAP_USER_ATTR_MAP'] = {
            'first_name': 'givenName',
            'last_name': 'sn',
            'email': 'mail',
        }
        g['AUTH_LDAP_GROUP_TYPE'] = GroupOfNamesType()

        if user_search_base:
            g['AUTH_LDAP_USER_SEARCH'] = LDAPSearch(
                user_search_base,
                getattr(ldap, 'SCOPE_SUBTREE'),
                user_filter,
            )
        if group_search_base:
            g['AUTH_LDAP_GROUP_SEARCH'] = LDAPSearch(
                group_search_base,
                getattr(ldap, 'SCOPE_SUBTREE'),
                '(objectClass=groupOfNames)',
            )

        # django-auth-ldap needs AUTH_LDAP_GROUP_SEARCH for USER_FLAGS_BY_GROUP
        # (ImproperlyConfigured at login otherwise). The populate_user handler
        # below sets the flags in any case.
        user_flags = {}
        if group_search_base:
            if staff_dn:
                user_flags['is_staff'] = staff_dn
            if superuser_dn:
                user_flags['is_superuser'] = superuser_dn
        elif staff_dn or superuser_dn:
            logger.info('LDAP_GROUP_SEARCH_BASE not set; staff/superuser flags are synced via populate_user only')
        g['AUTH_LDAP_USER_FLAGS_BY_GROUP'] = user_flags

        if staff_dn or superuser_dn or supervisor_dn or student_dn:
            from django_auth_ldap.backend import populate_user

            from users.ldap_membership import ldap_group_membership

            def _ldap_sync_custom_flags(sender, user=None, ldap_user=None, **kwargs):
                try:
                    if user is None or ldap_user is None:
                        return
                    try:
                        dns = set(ldap_user.group_dns or [])
                    except Exception:
                        # No AUTH_LDAP_GROUP_SEARCH configured or search failed
                        dns = set()
                    user_uid = None
                    try:
                        user_uid = getattr(ldap_user, 'attrs', {}).get('uid', [None])[0]
                        if user_uid:
                            user_uid = user_uid.decode('utf-8') if isinstance(user_uid, (bytes, bytearray)) else str(user_uid)
                    except Exception:
                        pass
                    try:
                        ldap_conn = ldap_user.connection
                    except Exception:
                        ldap_conn = None

                    flag_specs = (
                        ('is_staff', staff_dn),
                        ('is_superuser', superuser_dn),
                        ('is_supervisor', supervisor_dn),
                        ('is_student', student_dn),
                    )
                    for attr, group_dn in flag_specs:
                        if not group_dn:
                            continue
                        method = ldap_group_membership(
                            ldap_conn,
                            group_dn,
                            user_dn=getattr(ldap_user, 'dn', None),
                            user_uid=user_uid,
                            known_group_dns=dns,
                        )
                        new_val = bool(method)
                        logger.info(
                            'LDAP flag %s for %s: %s%s',
                            attr, user.get_username(), new_val, f' (via {method})' if method else '',
                        )
                        # The backend saves the user right after this signal
                        setattr(user, attr, new_val)
                except Exception:
                    logger.warning('LDAP custom flag sync failed', exc_info=True)

            # weak=False: the receiver is a local closure and would otherwise be
            # garbage-collected as soon as this function returns (never called).
            populate_user.connect(
                _ldap_sync_custom_flags,
                weak=False,
                dispatch_uid='ostdata_ldap_sync_custom_flags',
            )
    except Exception:
        logger.warning('LDAP configuration failed', exc_info=True)
