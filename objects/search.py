"""Object name and alias search helpers."""
from __future__ import annotations

from django.db.models import Q, Value
from django.db.models.functions import Replace

from objects.models import Identifier

# Django uses different names for ORM lookups vs prefetch / Python access.
IDENTIFIER_LOOKUP = 'identifier'
IDENTIFIER_PREFETCH = 'identifier_set'


def normalize_search_term(search: str) -> str:
    return (search or '').strip()


def object_ids_matching_alias_nospace(s_ns: str):
    """Object PKs whose identifier names match with spaces removed."""
    if not s_ns:
        return Identifier.objects.none().values('obj_id')
    return (
        Identifier.objects.annotate(
            name_nospace=Replace('name', Value(' '), Value('')),
        )
        .filter(name_nospace__icontains=s_ns)
        .values('obj_id')
    )


def build_object_search_q(search: str) -> Q:
    """
    Match object primary name or any Identifier alias (case-insensitive).
    Also matches with spaces removed from query and stored names.
    """
    s = normalize_search_term(search)
    if not s:
        return Q()
    s_ns = s.replace(' ', '')
    q = Q(name__icontains=s) | Q(**{f'{IDENTIFIER_LOOKUP}__name__icontains': s})
    if s_ns:
        q = q | Q(name_nospace__icontains=s_ns) | Q(pk__in=object_ids_matching_alias_nospace(s_ns))
    return q


def annotate_object_name_nospace(queryset):
    return queryset.annotate(name_nospace=Replace('name', Value(' '), Value('')))


def find_search_match_via(obj, search: str) -> str | None:
    """
    If the search term matched via an alias but not the primary object name,
    return the matching alias string; otherwise None.
    """
    s = normalize_search_term(search).lower()
    if not s:
        return None
    s_ns = s.replace(' ', '')

    def _matches(text: str) -> bool:
        t = (text or '').lower()
        t_ns = t.replace(' ', '')
        return s in t or (bool(s_ns) and s_ns in t_ns)

    if _matches(obj.name):
        return None

    best = None
    for ident in obj.identifier_set.all():
        iname = ident.name or ''
        if _matches(iname):
            if best is None or len(iname) < len(best):
                best = iname
    return best
