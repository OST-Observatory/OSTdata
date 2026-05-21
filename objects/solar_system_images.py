"""Storage and lookup for solar-system object preview images."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings

ALLOWED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
ALLOWED_UPLOAD_CONTENT_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
}


def sanitize_object_image_stem(name: str) -> str:
    """
    Build a safe filename stem from an object name.
    Spaces -> underscores; parentheses/brackets removed; unsafe chars stripped.
    """
    s = (name or '').strip()
    if not s:
        return 'object'
    s = re.sub(r'[\(\)\[\]\{\}]', '', s)
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^\w\-.]+', '_', s, flags=re.UNICODE)
    s = re.sub(r'_+', '_', s).strip('_.')
    return s or 'object'


def get_images_directory() -> Path:
    root = getattr(settings, 'SOLAR_SYSTEM_OBJECT_IMAGES_DIR', None)
    if not root:
        from ostdata.settings_base import BASE_DIR
        root = BASE_DIR / 'data' / 'solar_system_images'
    path = Path(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_image_path_for_stem(stem: str) -> Optional[Path]:
    directory = get_images_directory()
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        candidate = directory / f'{stem}{ext}'
        if candidate.is_file():
            return candidate
    return None


def find_image_path_for_object(obj) -> Optional[Path]:
    if getattr(obj, 'object_type', None) != 'SO':
        return None
    stem = sanitize_object_image_stem(getattr(obj, 'name', '') or '')
    return find_image_path_for_stem(stem)


def image_info_for_object(obj, request=None) -> Tuple[bool, Optional[str], str]:
    """Return (has_image, url_or_none, sanitized_stem)."""
    stem = sanitize_object_image_stem(getattr(obj, 'name', '') or '')
    path = find_image_path_for_stem(stem)
    if not path or getattr(obj, 'object_type', None) != 'SO':
        return False, None, stem
    url = None
    if request is not None:
        from django.urls import reverse
        url = request.build_absolute_uri(
            reverse('objects-api:object_solar_image', kwargs={'pk': obj.pk})
        )
    return True, url, stem


def save_image_for_object(obj, uploaded_file) -> Path:
    """Persist upload; replaces any existing image for this object's stem."""
    stem = sanitize_object_image_stem(getattr(obj, 'name', '') or '')
    original = (getattr(uploaded_file, 'name', '') or '').lower()
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/gif': '.gif',
        }
        ext = ext_map.get(content_type, '.jpg')
    directory = get_images_directory()
    for old_ext in ALLOWED_IMAGE_EXTENSIONS:
        old = directory / f'{stem}{old_ext}'
        if old.is_file():
            old.unlink()
    dest = directory / f'{stem}{ext}'
    with dest.open('wb') as out:
        for chunk in uploaded_file.chunks():
            out.write(chunk)
    return dest


def delete_image_for_object(obj) -> bool:
    path = find_image_path_for_object(obj)
    if path and path.is_file():
        path.unlink()
        return True
    return False
