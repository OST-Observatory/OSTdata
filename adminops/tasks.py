from __future__ import annotations

import logging

from celery import shared_task

from adminops.retention import pseudonymise_personal_data

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def pseudonymise_old_audit_data(self, dry_run: bool = True):
    """Remove the acting user from history/audit entries older than PERSONAL_DATA_RETENTION_DAYS."""
    result = pseudonymise_personal_data(dry_run=dry_run)
    logger.info(
        "Pseudonymise audit data complete (dry_run=%s): history=%s audit_log=%d user_role=%d",
        dry_run, result['history'], result['audit_log'], result['user_role'],
    )
    return result
