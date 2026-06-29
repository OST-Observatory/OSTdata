"""SER (.ser) video frame extraction and cached PNG thumbnails."""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import numpy as np
from django.conf import settings

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

logger = logging.getLogger(__name__)


def is_ser_path(file_type: str | None, file_path: Path) -> bool:
    ft = (file_type or '').upper()
    return ft == 'SER' or file_path.suffix.lower() == '.ser'


def _cache_dir() -> Path:
    base = getattr(settings, 'SER_THUMBNAIL_CACHE_DIR', None)
    if base:
        return Path(base)
    return Path(settings.BASE_DIR) / 'data' / 'ser_thumbnails'


def _cache_path(datafile_id: int, content_hash: str, max_dim: int) -> Path:
    digest = (content_hash or 'nohash').strip() or 'nohash'
    return _cache_dir() / f'df{datafile_id}_{digest}_w{max_dim}.png'


def _frame_to_uint8(arr: np.ndarray) -> np.ndarray:
    data = np.asarray(arr, dtype=np.float64)
    if data.ndim == 3 and data.shape[2] == 3:
        # OpenCV debayer paths return BGR; PIL expects RGB.
        data = data[:, :, ::-1]
    elif data.ndim == 3:
        data = data[..., 0]

    finite = np.isfinite(data)
    if not finite.any():
        raise ValueError('SER frame has no finite pixels')

    vmin, vmax = np.percentile(data[finite], [1.0, 99.5])
    if vmax <= vmin:
        vmax = vmin + 1.0
    scaled = np.clip((data - vmin) / (vmax - vmin), 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8)


def render_ser_frame_png(file_path: Path, max_dim: int = 512, frame_index: int | None = None) -> bytes:
    """Extract one SER frame and return PNG bytes."""
    if Image is None:
        raise RuntimeError('PIL not available')

    from obs_run.ser_parser import SERParser

    parser = SERParser(str(file_path))
    try:
        if parser.frame_count <= 0:
            raise ValueError('SER file has no frames')
        if frame_index is None:
            frame_index = parser.frame_count // 2
        frame_index = max(0, min(frame_index, parser.frame_count - 1))
        frame = parser.read_frame(frame_index)
        img8 = _frame_to_uint8(frame)
        mode = 'L' if img8.ndim == 2 else 'RGB'
        img = Image.fromarray(img8, mode=mode)
        img.thumbnail((max_dim, max_dim))
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    finally:
        parser.release()


def get_ser_thumbnail_png(
    *,
    datafile_id: int,
    content_hash: str,
    file_path: Path,
    max_dim: int = 512,
) -> bytes:
    """
    Return cached PNG thumbnail for a SER file, generating on cache miss.
    Cache invalidates when the source file is newer than the cached PNG.
    """
    cache_path = _cache_path(datafile_id, content_hash, max_dim)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        src_mtime = file_path.stat().st_mtime
    except OSError as exc:
        raise FileNotFoundError(str(file_path)) from exc

    if cache_path.is_file():
        try:
            if cache_path.stat().st_mtime >= src_mtime:
                return cache_path.read_bytes()
        except OSError:
            pass

    png = render_ser_frame_png(file_path, max_dim=max_dim)
    try:
        cache_path.write_bytes(png)
    except OSError:
        logger.warning('Could not write SER thumbnail cache %s', cache_path, exc_info=True)
    return png
