"""
Helpers for django-simple-history change reasons (audit log context).
"""
from __future__ import annotations

from simple_history.utils import update_change_reason

# API (user-facing)
REASON_API_OBJECT_PATCH = 'api:object_patch'
REASON_API_OBJECT_CREATE = 'api:object_create'
REASON_API_RUN_PATCH = 'api:run_patch'
REASON_API_TAG_CREATE = 'api:tag_create'
REASON_API_TAG_PATCH = 'api:tag_patch'
REASON_API_TAG_DELETE = 'api:tag_delete'

# Admin endpoints
REASON_ADMIN_RUN_SET_DATE = 'admin:run_set_date'
REASON_ADMIN_RUN_RECOMPUTE_DATE = 'admin:run_recompute_date'
REASON_ADMIN_CLEAR_OVERRIDE = 'admin:clear_override'
REASON_ADMIN_CLEAR_ALL_OVERRIDES = 'admin:clear_all_overrides'
REASON_ADMIN_EXPOSURE_TYPE_USER = 'admin:exposure_type_user'
REASON_ADMIN_SPECTROGRAPH = 'admin:spectrograph'
REASON_ADMIN_DELETE_ALIASES = 'admin:delete_aliases'
REASON_ADMIN_SIMBAD_IDENTIFIERS = 'admin:simbad_identifiers'
REASON_ADMIN_LINK_DATAFILES = 'admin:link_datafiles'
REASON_ADMIN_UNLINK_DATAFILES = 'admin:unlink_datafiles'

# Background tasks
REASON_TASK_SCAN_MISSING_RUN_JD = 'task:scan_missing:recompute_run_jd'
REASON_TASK_ORPHAN_OBJECTS_FIRST_HJD = 'task:orphan_objects:update_first_hjd'
REASON_TASK_PLATE_SOLVE = 'task:plate_solve'
REASON_TASK_ANALYZE_HEADER = 'task:analyze_header'


def set_instance_change_reason(instance, reason: str | None) -> None:
    """Set change reason on the next save for this instance."""
    if reason:
        instance._change_reason = reason


def apply_history_reason(instance, reason: str | None) -> None:
    """Attach reason to the most recent history row (after save)."""
    if not reason:
        return
    try:
        update_change_reason(instance, reason)
    except Exception:
        pass


def save_with_reason(instance, reason: str | None, **save_kwargs):
    """Save and ensure the latest history entry carries reason."""
    set_instance_change_reason(instance, reason)
    instance.save(**save_kwargs)
    apply_history_reason(instance, reason)
