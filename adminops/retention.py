"""
Retention for the change history and the admin audit log.

After PERSONAL_DATA_RETENTION_DAYS both keep *what* changed (provenance of the data) but no
longer *who* changed it: `history_user` / `AuditLogEntry.user` are set to NULL. Audit entries
about user accounts (`model_type='user_role'`) also carry the affected account's username and
old/new profile values; those are replaced as well.

The period is stated in the central privacy policy (landing page, #data-archive) — change both
together.
"""
from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from adminops.models import AuditLogEntry

PSEUDONYMISED = '(pseudonymised)'

# Profile fields logged by users.api.admin_views (_AUDIT_USER_FIELDS) that identify a person.
_PERSONAL_USER_FIELDS = {'email', 'first_name', 'last_name', 'note'}


def retention_cutoff(days: int | None = None):
    if days is None:
        days = settings.PERSONAL_DATA_RETENTION_DAYS
    return timezone.now() - timedelta(days=days)


def history_models():
    """All django-simple-history models (they are the ones with a `history_user` FK)."""
    result = []
    for model in apps.get_models():
        try:
            model._meta.get_field('history_user')
        except Exception:
            continue
        result.append(model)
    return result


def _pseudonymise_changes(changes):
    if not isinstance(changes, list):
        return changes
    cleaned = []
    for change in changes:
        if isinstance(change, dict) and change.get('field') in _PERSONAL_USER_FIELDS:
            change = {**change, 'old': None, 'new': None}
        cleaned.append(change)
    return cleaned


def pseudonymise_personal_data(days: int | None = None, dry_run: bool = False) -> dict:
    """Remove the link to persons from history and audit entries older than the cutoff.

    Returns counts per table; with dry_run=True nothing is written.
    """
    cutoff = retention_cutoff(days)
    result = {'cutoff': cutoff.isoformat(), 'dry_run': dry_run, 'history': {}, 'audit_log': 0, 'user_role': 0}

    with transaction.atomic():
        for model in history_models():
            qs = model.objects.filter(history_date__lt=cutoff, history_user__isnull=False)
            count = qs.count() if dry_run else qs.update(history_user=None)
            if count:
                result['history'][model._meta.label] = count

        old = AuditLogEntry.objects.filter(created_at__lt=cutoff)

        audit_qs = old.filter(user__isnull=False)
        result['audit_log'] = audit_qs.count() if dry_run else audit_qs.update(user=None)

        user_role_qs = old.filter(model_type='user_role').exclude(entity_label=PSEUDONYMISED)
        if dry_run:
            result['user_role'] = user_role_qs.count()
        else:
            for entry in user_role_qs.only('pk', 'action', 'changes'):
                entry.entity_label = PSEUDONYMISED
                entry.summary = f'User {PSEUDONYMISED} {entry.action}'
                entry.changes = _pseudonymise_changes(entry.changes)
                entry.save(update_fields=['entity_label', 'summary', 'changes'])
                result['user_role'] += 1

    return result
