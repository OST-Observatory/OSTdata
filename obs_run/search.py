"""Observation run search helpers (auxiliary SIMBAD objects)."""
from __future__ import annotations

import re

from django.db.models import Q

from objects.search import normalize_search_term
from obs_run.models import ObservationRun


def _name_matches_search(name: str, search: str) -> bool:
    s = normalize_search_term(search).lower()
    if not s:
        return False
    s_ns = s.replace(' ', '')
    n = (name or '').lower()
    n_ns = n.replace(' ', '')
    return s in n or (bool(s_ns) and s_ns in n_ns)


def _spaced_name_variant(search: str) -> str:
    """Insert spaces at alpha/numeric boundaries (M31 -> M 31)."""
    return re.sub(r'(?<=\D)(?=\d)|(?<=\d)(?=\D)', ' ', search.strip()).strip()


def build_run_aux_objects_search_q(search: str) -> Q:
    """
    Match runs whose cached aux_objects list contains an object name matching search.

    DB filter uses JSON text icontains on the ``name`` field plus a ready-status guard.
    """
    s = normalize_search_term(search)
    if not s:
        return Q()

    base = Q(aux_objects_status=ObservationRun.AUX_STATUS_READY) & ~Q(aux_objects=[])

    q = Q()
    variants = {s, s.lower(), s.upper(), _spaced_name_variant(s)}
    s_ns = s.replace(' ', '')
    if s_ns:
        variants.add(s_ns)

    for term in variants:
        if not term:
            continue
        # Full or prefix match at start of SIMBAD name
        q |= Q(aux_objects__icontains=f'"name": "{term}')
        q |= Q(aux_objects__icontains=f'"name":"{term}')
        # Partial match inside the name (e.g. "T Tau" in "V* T Tau")
        if len(term) >= 2:
            q |= Q(aux_objects__icontains=f' {term}"')

    return base & q


def find_aux_object_search_match(run: ObservationRun, search: str) -> str | None:
    """Return the matching auxiliary object name when search hit aux_objects."""
    s = normalize_search_term(search)
    if not s or run.aux_objects_status != ObservationRun.AUX_STATUS_READY:
        return None

    best = None
    for obj in run.aux_objects or []:
        name = obj.get('name') or ''
        if not _name_matches_search(name, s):
            continue
        if best is None or len(name) < len(best):
            best = name
    return best
