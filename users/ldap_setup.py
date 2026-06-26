"""LDAP configuration extracted from Django settings."""
import logging
import os

logger = logging.getLogger(__name__)


def configure_ldap_from_env(g, env):
    """Apply LDAP auth backend settings when AUTH_LDAP_SERVER_URI is configured."""
    server_uri = g.get('AUTH_LDAP_SERVER_URI') or ''
    if not server_uri:
        return

    connect_timeout = g.get('AUTH_LDAP_CONNECT_TIMEOUT', 5)
    bind_dn = g.get('AUTH_LDAP_BIND_DN', '')
    bind_password = g.get('AUTH_LDAP_BIND_PASSWORD', '')
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
            ldap.OPT_NETWORK_TIMEOUT: connect_timeout,
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
                ldap.SCOPE_SUBTREE,
                user_filter,
            )
        if group_search_base:
            g['AUTH_LDAP_GROUP_SEARCH'] = LDAPSearch(
                group_search_base,
                ldap.SCOPE_SUBTREE,
                '(objectClass=groupOfNames)',
            )

        user_flags = {}
        if staff_dn:
            user_flags['is_staff'] = staff_dn
        if superuser_dn:
            user_flags['is_superuser'] = superuser_dn
        g['AUTH_LDAP_USER_FLAGS_BY_GROUP'] = user_flags

        if staff_dn or superuser_dn or supervisor_dn or student_dn:
            from django_auth_ldap.backend import populate_user

            def _check_ldap_group_membership_via_memberuid(group_dn, user_uid, ldap_conn=None):
                if not group_dn or not user_uid:
                    return False
                conn = ldap_conn
                should_close = False
                try:
                    if conn is None:
                        import ldap as ldap_module
                        from django.conf import settings as django_settings

                        uri = getattr(django_settings, 'AUTH_LDAP_SERVER_URI', None) or os.environ.get('LDAP_SERVER_URI')
                        if not uri:
                            return False
                        conn = ldap_module.initialize(uri)
                        conn.set_option(ldap_module.OPT_REFERRALS, 0)
                        start_tls = bool(
                            getattr(django_settings, 'AUTH_LDAP_START_TLS', False)
                            or str(os.environ.get('LDAP_START_TLS', 'false')).lower() in ('1', 'true', 'yes')
                        )
                        if start_tls:
                            try:
                                conn.start_tls_s()
                            except Exception:
                                logger.debug('LDAP STARTTLS failed', exc_info=True)
                        bdn = getattr(django_settings, 'AUTH_LDAP_BIND_DN', None) or os.environ.get('LDAP_BIND_DN') or ''
                        bpw = getattr(django_settings, 'AUTH_LDAP_BIND_PASSWORD', None) or os.environ.get('LDAP_BIND_PASSWORD') or ''
                        try:
                            if bdn:
                                conn.simple_bind_s(bdn, bpw or '')
                            else:
                                conn.simple_bind_s()
                        except Exception:
                            logger.warning('LDAP bind failed during memberUid check', exc_info=True)
                            return False
                        should_close = True
                    try:
                        import ldap as ldap_module

                        result = conn.search_s(group_dn, ldap_module.SCOPE_BASE, '(objectClass=*)', ['memberUid'])
                        if result:
                            _, group_vals = result[0]
                            member_uids = group_vals.get('memberUid', [])
                            member_uids_str = []
                            for uid in member_uids or []:
                                try:
                                    member_uids_str.append(
                                        uid.decode('utf-8') if isinstance(uid, (bytes, bytearray)) else str(uid)
                                    )
                                except Exception:
                                    member_uids_str.append(str(uid))
                            return user_uid in member_uids_str
                    except Exception:
                        logger.debug('LDAP memberUid group read failed', exc_info=True)
                except Exception:
                    logger.debug('LDAP memberUid membership check failed', exc_info=True)
                finally:
                    if should_close and conn:
                        try:
                            conn.unbind_s()
                        except Exception:
                            pass
                return False

            def _ldap_sync_custom_flags(sender, user=None, ldap_user=None, **kwargs):
                try:
                    dns = set(ldap_user.group_dns or [])
                    dirty = False
                    user_uid = None
                    try:
                        user_uid = getattr(ldap_user, 'attrs', {}).get('uid', [None])[0]
                        if user_uid:
                            user_uid = user_uid.decode('utf-8') if isinstance(user_uid, (bytes, bytearray)) else str(user_uid)
                    except Exception:
                        pass
                    ldap_conn = getattr(ldap_user, '_connection', None)

                    flag_specs = (
                        ('is_staff', staff_dn),
                        ('is_superuser', superuser_dn),
                        ('is_supervisor', supervisor_dn),
                        ('is_student', student_dn),
                    )
                    for attr, group_dn in flag_specs:
                        if not group_dn:
                            continue
                        new_val = any(d.lower() == group_dn.lower() for d in dns)
                        if not new_val and user_uid:
                            new_val = _check_ldap_group_membership_via_memberuid(group_dn, user_uid, ldap_conn)
                        if getattr(user, attr, False) != new_val:
                            setattr(user, attr, new_val)
                            dirty = True

                    if dirty:
                        update_fields = [attr for attr, group_dn in flag_specs if group_dn]
                        if update_fields:
                            user.save(update_fields=update_fields)
                except Exception:
                    logger.warning('LDAP custom flag sync failed', exc_info=True)

            populate_user.connect(_ldap_sync_custom_flags)
    except Exception:
        logger.warning('LDAP configuration failed', exc_info=True)
