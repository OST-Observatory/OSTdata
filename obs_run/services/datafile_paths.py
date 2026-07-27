"""Resolve filesystem paths under DATA_DIRECTORY (path jail)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from django.conf import settings


class PathOutsideDataRoot(ValueError):
    """Raised when a path resolves outside the configured data root."""


def get_data_root() -> Path:
    root = getattr(settings, 'DATA_DIRECTORY', None)
    if not root:
        raise PathOutsideDataRoot('DATA_DIRECTORY is not configured')
    return Path(root).resolve()


def resolve_under_data_root(
    path: Union[str, Path],
    *,
    must_exist: bool = False,
) -> Path:
    """
    Resolve path and ensure it stays under DATA_DIRECTORY.
    Rejects symlink escapes via resolve().
    """
    if path is None or str(path).strip() == '':
        raise PathOutsideDataRoot('Empty path')
    root = get_data_root()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathOutsideDataRoot(f'Path outside DATA_DIRECTORY: {path}') from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def safe_datafile_path(datafile_field: Optional[str], *, must_exist: bool = False) -> Path:
    """Resolve a DataFile.datafile field value under the data root."""
    return resolve_under_data_root(datafile_field or '', must_exist=must_exist)
