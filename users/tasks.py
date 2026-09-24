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
