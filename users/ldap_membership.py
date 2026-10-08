"""LDAP group membership check shared by login flag sync and the admin LDAP test."""
import logging

logger = logging.getLogger(__name__)

# Group member attributes holding full user DNs (groupOfNames / groupOfUniqueNames)
_MEMBER_DN_ATTRS = ('member', 'uniqueMember')


def _to_str(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='replace')
    return str(value)


def normalize_dn(dn):
    """Normalize a DN for comparison (case and whitespace after separators)."""
    if not dn:
        return ''
    dn = _to_str(dn)
    try:
        import ldap.dn  # type: ignore
        return ldap.dn.dn2str(ldap.dn.str2dn(dn)).lower()
    except Exception:
        return ','.join(part.strip() for part in dn.split(',')).lower()


def ldap_group_membership(conn, group_dn, user_dn=None, user_uid=None, known_group_dns=()):
    """
    Return the method by which the user was found in group_dn, or '' if not a member.

    Checks, in order:
      1. known_group_dns (memberOf values or groups from AUTH_LDAP_GROUP_SEARCH)
      2. server-side compare of member / uniqueMember with the user DN
      3. memberUid (posixGroup) with the user uid
    """
    if not group_dn:
        return ''
    target = normalize_dn(group_dn)
    if any(normalize_dn(d) == target for d in (known_group_dns or ())):
        return 'group_dn'
    if conn is None:
        return ''

    if user_dn:
        for attr in _MEMBER_DN_ATTRS:
            try:
                if conn.compare_s(group_dn, attr, _to_str(user_dn).encode('utf-8')):
                    return attr
            except Exception:
                # NO_SUCH_ATTRIBUTE / UNDEFINED_TYPE / NO_SUCH_OBJECT etc. -> not via this attr
                logger.debug('LDAP compare %s on %s failed', attr, group_dn, exc_info=True)

    if user_uid:
        try:
            import ldap  # type: ignore
            result = conn.search_s(group_dn, ldap.SCOPE_BASE, '(objectClass=*)', ['memberUid'])
            if result:
                group_vals = result[0][1] if isinstance(result[0], (tuple, list)) and len(result[0]) >= 2 else {}
                if user_uid in [_to_str(uid) for uid in (group_vals.get('memberUid') or [])]:
                    return 'memberUid'
        except Exception:
            logger.debug('LDAP memberUid read on %s failed', group_dn, exc_info=True)

    return ''
