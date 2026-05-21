"""
Admin audit log: django-simple-history + explicit AuditLogEntry events.

Performance: SQL UNION ALL for ordering; hydrate only capped rows; optional
batch grouping for automated DataFile history noise.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from adminops.models import AuditLogEntry
from objects.models import Identifier, Object
from obs_run.models import DataFile, ObservationRun
from tags.models import Tag

User = get_user_model()

MAX_AUDIT_ENTRIES = 1000
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

BATCH_GROUP_MIN_COUNT = 3
BATCH_GROUP_WINDOW_SEC = 60

HISTORY_MODEL_TYPES = frozenset({
    'object',
    'identifier',
    'observation_run',
    'datafile',
    'tag',
})

EVENT_MODEL_TYPES = frozenset({
    'acl',
    'banner',
    'download_job',
    'solar_image',
    'tag_assignment',
    'user_role',
})

VALID_ACTIONS = frozenset({'created', 'updated', 'deleted', 'done', 'failed'})

VALID_MODEL_TYPES = HISTORY_MODEL_TYPES | EVENT_MODEL_TYPES

VALID_DAYS = frozenset({7, 30, 90})

HISTORY_SKIP_FIELDS = frozenset({
    'history_id',
    'history_date',
    'history_user',
    'history_user_id',
    'history_change_reason',
    'history_type',
})


@dataclass(frozen=True)
class AuditRef:
    ref_id: int
    ts: datetime
    model_type: str
    ref_kind: str  # 'hist' | 'evt'


def _datafile_label(record) -> str:
    path = getattr(record, 'datafile', None) or ''
    if path:
        return Path(str(path)).name
    return f'Data file #{record.id}'


def _datafile_entity_path(record) -> str:
    run_id = getattr(record, 'observation_run_id', None)
    if run_id:
        return f'/observation-runs/{run_id}'
    return '/datafiles'


AUDIT_SOURCES: list[dict[str, Any]] = [
    {
        'model_type': 'object',
        'model_label': 'Object',
        'model': Object,
        'display': lambda r: getattr(r, 'name', None) or f'Object #{r.id}',
        'entity_path': lambda r: f'/objects/{r.id}',
    },
    {
        'model_type': 'identifier',
        'model_label': 'Identifier',
        'model': Identifier,
        'display': lambda r: getattr(r, 'name', None) or f'Identifier #{r.id}',
        'entity_path': lambda r: f'/objects/{r.obj_id}',
    },
    {
        'model_type': 'observation_run',
        'model_label': 'Observation run',
        'model': ObservationRun,
        'display': lambda r: getattr(r, 'name', None) or f'Run #{r.id}',
        'entity_path': lambda r: f'/observation-runs/{r.id}',
    },
    {
        'model_type': 'datafile',
        'model_label': 'Data file',
        'model': DataFile,
        'display': _datafile_label,
        'entity_path': _datafile_entity_path,
    },
    {
        'model_type': 'tag',
        'model_label': 'Tag',
        'model': Tag,
        'display': lambda r: getattr(r, 'name', None) or f'Tag #{r.id}',
        'entity_path': lambda r: '/tags',
    },
]

SOURCE_BY_TYPE = {s['model_type']: s for s in AUDIT_SOURCES}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _parse_action(value: Any) -> str | None:
    if value is None or value == '':
        return None
    action = str(value).strip().lower()
    return action if action in VALID_ACTIONS else None


def _parse_search(value: Any) -> str | None:
    if value is None:
        return None
    q = str(value).strip()
    return q if q else None


def _parse_days(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return days if days in VALID_DAYS else None


def _is_override_field(field_name: str) -> bool:
    return field_name.endswith('_override')


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return value.isoformat()
        return timezone.make_aware(value, timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _history_action(history_type: str) -> str:
    if history_type == '+':
        return 'created'
    if history_type == '-':
        return 'deleted'
    return 'updated'


def _build_changes(record, *, hide_override_fields: bool = False) -> list[dict[str, Any]]:
    history_type = record.history_type
    if history_type == '+':
        return [{'field': '__created__', 'old': None, 'new': None}]
    if history_type == '-':
        return [{'field': '__deleted__', 'old': None, 'new': None}]
    prev = record.prev_record
    if not prev:
        return []
    try:
        delta = record.diff_against(prev)
    except Exception:
        return []
    changes = []
    for change in delta.changes:
        if change.field in HISTORY_SKIP_FIELDS:
            continue
        if hide_override_fields and _is_override_field(change.field):
            continue
        changes.append({
            'field': change.field,
            'old': _serialize_value(change.old),
            'new': _serialize_value(change.new),
        })
    return changes


def _is_user_change(record) -> bool:
    if getattr(record, 'history_user_id', None):
        return True
    return getattr(record, 'history_user', None) is not None


def _user_display(
    record,
    users_by_id: dict[int, Any] | None = None,
) -> tuple[dict[str, Any] | None, str]:
    user = getattr(record, 'history_user', None)
    user_id = getattr(record, 'history_user_id', None)
    if user is None and user_id and users_by_id is not None:
        user = users_by_id.get(user_id)
    if user is None and user_id and users_by_id is None:
        try:
            user = User.objects.filter(pk=user_id).only('id', 'username', 'email').first()
        except Exception:
            user = None
    if user is None:
        return None, 'System'
    return {
        'id': user.id,
        'username': getattr(user, 'username', '') or '',
        'email': getattr(user, 'email', '') or '',
    }, getattr(user, 'username', None) or getattr(user, 'email', None) or f'User #{user.id}'


def _user_display_from_user(user) -> tuple[dict[str, Any] | None, str]:
    if user is None:
        return None, 'System'
    return {
        'id': user.id,
        'username': getattr(user, 'username', '') or '',
        'email': getattr(user, 'email', '') or '',
    }, getattr(user, 'username', None) or getattr(user, 'email', None) or f'User #{user.id}'


def _normalize_history_record(
    record,
    source: dict[str, Any],
    *,
    hide_override_fields: bool = False,
    users_by_id: dict[int, Any] | None = None,
) -> dict[str, Any]:
    user_payload, user_display = _user_display(record, users_by_id=users_by_id)
    changes = _build_changes(record, hide_override_fields=hide_override_fields)
    action = _history_action(record.history_type)
    history_date = record.history_date
    if history_date and timezone.is_naive(history_date):
        history_date = timezone.make_aware(history_date, timezone.utc)
    ts = history_date.isoformat() if history_date else None
    reason = getattr(record, 'history_change_reason', None) or None
    if reason is not None:
        reason = str(reason).strip() or None
    has_field_changes = bool(changes) or action in ('created', 'deleted')
    return {
        'id': f"{source['model_type']}:{record.history_id}",
        'history_id': record.history_id,
        'model_type': source['model_type'],
        'model_label': source['model_label'],
        'instance_id': record.id,
        'entity_label': source['display'](record),
        'entity_path': source['entity_path'](record),
        'timestamp': ts,
        'history_type': record.history_type,
        'action': action,
        'change_reason': reason,
        'is_user_change': _is_user_change(record),
        'is_batch': False,
        'batch_count': 1,
        'user': user_payload,
        'user_display': user_display,
        'changes': changes,
        'has_field_changes': has_field_changes,
        '_sort_ts': history_date,
    }


def _normalize_event_record(entry: AuditLogEntry, users_by_id: dict[int, Any]) -> dict[str, Any]:
    user_payload, user_display = _user_display_from_user(
        users_by_id.get(entry.user_id) if entry.user_id else None
    )
    ts = entry.created_at
    if ts and timezone.is_naive(ts):
        ts = timezone.make_aware(ts, timezone.get_current_timezone())
    return {
        'id': f"evt:{entry.model_type}:{entry.pk}",
        'history_id': entry.pk,
        'model_type': entry.model_type,
        'model_label': entry.model_label,
        'instance_id': entry.instance_id,
        'entity_label': entry.entity_label,
        'entity_path': entry.entity_path or '',
        'timestamp': ts.isoformat() if ts else None,
        'history_type': '~',
        'action': entry.action,
        'change_reason': entry.change_reason or None,
        'is_user_change': entry.user_id is not None,
        'is_batch': entry.is_batch,
        'batch_count': entry.batch_count,
        'user': user_payload,
        'user_display': user_display,
        'changes': entry.changes if isinstance(entry.changes, list) else [],
        'has_field_changes': bool(entry.changes) or entry.action in ('created', 'deleted'),
        'summary': entry.summary or '',
        '_sort_ts': ts,
    }


def _entry_search_blob(entry: dict[str, Any]) -> str:
    parts = [
        entry.get('entity_label') or '',
        entry.get('user_display') or '',
        entry.get('change_reason') or '',
        entry.get('model_label') or '',
        entry.get('model_type') or '',
        entry.get('action') or '',
        entry.get('summary') or '',
    ]
    user = entry.get('user') or {}
    if isinstance(user, dict):
        parts.extend([user.get('username') or '', user.get('email') or ''])
    for ch in entry.get('changes') or []:
        parts.append(str(ch.get('field') or ''))
        parts.append(str(ch.get('old') or ''))
        parts.append(str(ch.get('new') or ''))
    return ' '.join(parts).lower()


def _entry_matches_search(entry: dict[str, Any], search: str | None) -> bool:
    if not search:
        return True
    tokens = search.lower().split()
    if not tokens:
        return True
    blob = _entry_search_blob(entry)
    return all(token in blob for token in tokens)


def _entry_matches_action(entry: dict[str, Any], action: str | None) -> bool:
    if not action:
        return True
    return entry.get('action') == action


def _apply_post_filters(
    entries: list[dict[str, Any]],
    *,
    action: str | None,
    search: str | None,
) -> list[dict[str, Any]]:
    return [
        e for e in entries
        if _entry_matches_action(e, action) and _entry_matches_search(e, search)
    ]


def _entry_visible(entry: dict[str, Any], *, hide_override_fields: bool) -> bool:
    if not hide_override_fields:
        return True
    if entry['action'] in ('created', 'deleted'):
        return True
    return entry['has_field_changes']


def _filter_history_sources(model_type: str | None) -> list[dict[str, Any]]:
    if model_type and model_type in HISTORY_MODEL_TYPES:
        return [s for s in AUDIT_SOURCES if s['model_type'] == model_type]
    if model_type and model_type in EVENT_MODEL_TYPES:
        return []
    return AUDIT_SOURCES


def _include_events(model_type: str | None) -> bool:
    if model_type is None:
        return True
    return model_type in EVENT_MODEL_TYPES


def _build_history_union_sql(
    sources: list[dict[str, Any]],
    *,
    since: datetime | None,
    user_only: bool,
    hide_system_datafiles: bool,
) -> tuple[str, list[Any]]:
    branches: list[str] = []
    params: list[Any] = []

    for source in sources:
        table = connection.ops.quote_name(source['model'].history.model._meta.db_table)
        wheres: list[str] = []
        if since is not None:
            wheres.append('history_date >= %s')
            params.append(since)
        if user_only:
            wheres.append('history_user_id IS NOT NULL')
        elif hide_system_datafiles and source['model_type'] == 'datafile':
            wheres.append('history_user_id IS NOT NULL')

        where_sql = f" WHERE {' AND '.join(wheres)}" if wheres else ''
        branches.append(
            f"SELECT history_id AS ref_id, history_date AS ts, %s AS audit_model_type, "
            f"'hist' AS ref_kind FROM {table}{where_sql}"
        )
        params.append(source['model_type'])

    if not branches:
        return '', []

    return ' UNION ALL '.join(branches), params


def _build_event_union_sql(
    *,
    since: datetime | None,
    user_only: bool,
    model_type: str | None,
) -> tuple[str, list[Any]]:
    table = connection.ops.quote_name(AuditLogEntry._meta.db_table)
    wheres: list[str] = []
    params: list[Any] = []

    if since is not None:
        wheres.append('created_at >= %s')
        params.append(since)
    if user_only:
        wheres.append('user_id IS NOT NULL')
    if model_type and model_type in EVENT_MODEL_TYPES:
        wheres.append('model_type = %s')
        params.append(model_type)

    where_sql = f" WHERE {' AND '.join(wheres)}" if wheres else ''
    sql = (
        f"SELECT id AS ref_id, created_at AS ts, model_type AS audit_model_type, "
        f"'evt' AS ref_kind FROM {table}{where_sql}"
    )
    return sql, params


def _build_combined_union_sql(
    *,
    model_type: str | None,
    since: datetime | None,
    user_only: bool,
    hide_system_datafiles: bool,
) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []

    hist_sql, hist_params = _build_history_union_sql(
        _filter_history_sources(model_type),
        since=since,
        user_only=user_only,
        hide_system_datafiles=hide_system_datafiles,
    )
    if hist_sql:
        parts.append(hist_sql)
        params.extend(hist_params)

    if _include_events(model_type):
        evt_sql, evt_params = _build_event_union_sql(
            since=since,
            user_only=user_only,
            model_type=model_type if model_type in EVENT_MODEL_TYPES else None,
        )
        parts.append(evt_sql)
        params.extend(evt_params)

    if not parts:
        return 'SELECT NULL AS ref_id, NULL AS ts, NULL AS audit_model_type, NULL AS ref_kind WHERE 1=0', []

    if len(parts) == 1:
        return parts[0], params
    return ' UNION ALL '.join(parts), params


def _refs_from_rows(rows: list[tuple]) -> list[AuditRef]:
    refs: list[AuditRef] = []
    for ref_id, ts, model_type, ref_kind in rows:
        if ref_id is None or model_type is None:
            continue
        dt = ts
        if dt and timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        refs.append(AuditRef(int(ref_id), dt, str(model_type), str(ref_kind or 'hist')))
    return refs


def _fetch_capped_refs(union_sql: str, params: list[Any], *, cap: int = MAX_AUDIT_ENTRIES) -> list[AuditRef]:
    sql = f"""
        SELECT ref_id, ts, audit_model_type, ref_kind
        FROM ({union_sql}) AS merged
        ORDER BY ts DESC
        LIMIT %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [*params, cap])
        return _refs_from_rows(cursor.fetchall())


def _load_users_for_history(records: list[Any]) -> dict[int, Any]:
    user_ids = {
        getattr(r, 'history_user_id', None)
        for r in records
        if getattr(r, 'history_user_id', None)
    }
    if not user_ids:
        return {}
    return {
        u.id: u
        for u in User.objects.filter(pk__in=user_ids).only('id', 'username', 'email')
    }


def _load_users_for_events(entries: list[AuditLogEntry]) -> dict[int, Any]:
    user_ids = {e.user_id for e in entries if e.user_id}
    if not user_ids:
        return {}
    return {
        u.id: u
        for u in User.objects.filter(pk__in=user_ids).only('id', 'username', 'email')
    }


def _hydrate_entries(
    refs: list[AuditRef],
    *,
    hide_override_fields: bool = False,
) -> list[dict[str, Any]]:
    if not refs:
        return []

    hist_ids: dict[str, list[int]] = defaultdict(list)
    evt_ids: list[int] = []

    for ref in refs:
        if ref.ref_kind == 'evt':
            evt_ids.append(ref.ref_id)
        else:
            hist_ids[ref.model_type].append(ref.ref_id)

    records_by_key: dict[tuple[str, int], Any] = {}
    all_history: list[Any] = []

    for model_type, history_ids in hist_ids.items():
        source = SOURCE_BY_TYPE.get(model_type)
        if not source:
            continue
        hist_model = source['model'].history.model
        for record in hist_model.objects.filter(history_id__in=history_ids).select_related('history_user'):
            records_by_key[(model_type, record.history_id)] = record
            all_history.append(record)

    events_by_id: dict[int, AuditLogEntry] = {}
    if evt_ids:
        for entry in AuditLogEntry.objects.filter(pk__in=evt_ids).select_related('user'):
            events_by_id[entry.pk] = entry

    users_by_id = _load_users_for_history(all_history)
    users_by_id.update(_load_users_for_events(list(events_by_id.values())))

    entries: list[dict[str, Any]] = []
    for ref in refs:
        if ref.ref_kind == 'evt':
            event = events_by_id.get(ref.ref_id)
            if event is None:
                continue
            entries.append(_normalize_event_record(event, users_by_id))
            continue
        record = records_by_key.get((ref.model_type, ref.ref_id))
        if record is None:
            continue
        source = SOURCE_BY_TYPE[ref.model_type]
        entries.append(
            _normalize_history_record(
                record,
                source,
                hide_override_fields=hide_override_fields,
                users_by_id=users_by_id,
            )
        )
    return entries


def _batch_group_key(entry: dict[str, Any]) -> tuple | None:
    if entry.get('is_batch'):
        return None
    if entry.get('model_type') != 'datafile':
        return None
    if entry.get('is_user_change'):
        return None
    if entry.get('action') != 'updated':
        return None
    ts = entry.get('_sort_ts')
    if not ts:
        return None
    bucket = int(ts.timestamp()) // BATCH_GROUP_WINDOW_SEC
    reason = entry.get('change_reason') or '__system__'
    return (entry['model_type'], reason, bucket)


def _make_batch_entry(group: list[dict[str, Any]]) -> dict[str, Any]:
    first = group[0]
    count = len(group)
    reason = first.get('change_reason') or 'automated update'
    reason_short = reason if len(reason) <= 48 else f'{reason[:45]}…'
    return {
        'id': f"batch:datafile:{reason}:{first.get('timestamp')}",
        'history_id': first.get('history_id'),
        'model_type': 'datafile',
        'model_label': 'Data file',
        'instance_id': None,
        'entity_label': f'{count} data files ({reason_short})',
        'entity_path': '/datafiles',
        'timestamp': first.get('timestamp'),
        'history_type': '~',
        'action': 'updated',
        'change_reason': reason,
        'is_user_change': False,
        'is_batch': True,
        'batch_count': count,
        'user': None,
        'user_display': 'System',
        'changes': [{
            'field': '__batch__',
            'old': None,
            'new': count,
        }],
        'has_field_changes': True,
        '_sort_ts': first.get('_sort_ts'),
    }


def _group_datafile_batches(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not entries:
        return entries
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        key = _batch_group_key(entry)
        if key is None:
            result.append(entry)
            i += 1
            continue
        group = [entry]
        j = i + 1
        while j < len(entries):
            next_key = _batch_group_key(entries[j])
            if next_key != key:
                break
            group.append(entries[j])
            j += 1
        if len(group) >= BATCH_GROUP_MIN_COUNT:
            result.append(_make_batch_entry(group))
        else:
            result.extend(group)
        i = j
    return result


def _collect_entries(
    *,
    model_type: str | None,
    user_only: bool,
    hide_system_datafiles: bool,
    hide_override_fields: bool,
    days: int | None,
    group_batches: bool,
    action: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    since = timezone.now() - timedelta(days=days) if days is not None else None
    union_sql, params = _build_combined_union_sql(
        model_type=model_type,
        since=since,
        user_only=user_only,
        hide_system_datafiles=hide_system_datafiles,
    )
    refs = _fetch_capped_refs(union_sql, params)

    entries: list[dict[str, Any]] = []
    chunk_size = 50
    for i in range(0, len(refs), chunk_size):
        chunk_entries = _hydrate_entries(refs[i:i + chunk_size], hide_override_fields=hide_override_fields)
        for entry in chunk_entries:
            if hide_system_datafiles and entry['model_type'] == 'datafile' and not entry['is_user_change']:
                continue
            if user_only and not entry['is_user_change']:
                continue
            if not _entry_visible(entry, hide_override_fields=hide_override_fields):
                continue
            entries.append(entry)

    if group_batches:
        entries = _group_datafile_batches(entries)

    entries = _apply_post_filters(entries, action=action, search=search)

    for item in entries:
        item.pop('_sort_ts', None)
    return entries[:MAX_AUDIT_ENTRIES]


def get_audit_log_page(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    *,
    model_type: str | None = None,
    user_only: bool = False,
    hide_system_datafiles: bool = True,
    hide_override_fields: bool = False,
    days: int | None = None,
    group_batches: bool = True,
    action: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    if model_type and model_type not in VALID_MODEL_TYPES:
        model_type = None
    days = _parse_days(days) if days is not None else None
    group_batches = _parse_bool(group_batches, default=True)
    action = _parse_action(action)
    search = _parse_search(search)

    all_entries = _collect_entries(
        model_type=model_type,
        user_only=user_only,
        hide_system_datafiles=hide_system_datafiles,
        hide_override_fields=hide_override_fields,
        days=days,
        group_batches=group_batches,
        action=action,
        search=search,
    )
    total = len(all_entries)
    start = (page - 1) * page_size
    end = start + page_size

    return {
        'count': total,
        'page': page,
        'page_size': page_size,
        'max_entries': MAX_AUDIT_ENTRIES,
        'filters': {
            'model_type': model_type,
            'user_only': user_only,
            'hide_system_datafiles': hide_system_datafiles,
            'hide_override_fields': hide_override_fields,
            'days': days,
            'group_batches': group_batches,
            'action': action,
            'search': search,
        },
        'results': all_entries[start:end],
    }
