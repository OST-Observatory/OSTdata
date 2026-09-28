from __future__ import annotations

import logging
from importlib import import_module

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def clear_expired_sessions(self):
    """Delete expired sessions (same as `manage.py clearsessions`).

    Django never removes expired rows from `django_session` on its own.
    """
    engine = import_module(settings.SESSION_ENGINE)
    engine.SessionStore.clear_expired()
    logger.info("Expired sessions cleared.")
    return {'cleared': True}


@shared_task(bind=True)
def deactivate_departed_ldap_users(self):
    """Deactivate accounts whose LDAP entry is gone (see users/departed.py).

    LDAP errors and the mass-deactivation safety stop are raised, so a failed run shows up in
    the worker log instead of silently changing nothing.
    """
    from users.departed import run_departed_check

    result = run_departed_check()
    if result is None:
        logger.info("Departed LDAP check skipped: LDAP not configured.")
        return {'skipped': True}
    logger.info(
        "Departed LDAP check complete: checked=%d deactivated=%s",
        result.checked, ', '.join(result.departed) or '-',
    )
    return {'checked': result.checked, 'deactivated': result.departed}
