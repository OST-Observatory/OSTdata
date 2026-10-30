"""AVI/MOV video frame extraction (OpenCV/FFmpeg) and cached PNG thumbnails."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from obs_run.ser_thumbnails import _frame_to_png, check_frame_pixels, get_cached_thumbnail_png

VIDEO_SUFFIXES = ('.avi', '.mov')


def is_video_path(file_type: str | None, file_path: Path) -> bool:
    ft = (file_type or '').upper()
    return ft in ('AVI', 'MOV') or file_path.suffix.lower() in VIDEO_SUFFIXES


# OpenCV's bundled FFmpeg can crash (SIGABRT/SIGSEGV) or hang on some videos that players handle fine:
# Gunicorn, Celery and the watchdog only open videos in the isolated reader process (file_check_worker)
VIDEO_READER_TIMEOUT = 60


def render_video_frame_png(file_path: Path, max_dim: int = 512, frame_index: int | None = None,
                           max_pixels: int | None = None) -> bytes:
    """Extract one frame (middle of the video by default) and return PNG bytes (in-process: see above)."""
    import cv2

    cap = cv2.VideoCapture(str(file_path))
    try:
        if not cap.isOpened():
            raise ValueError('Video file cannot be opened')
        check_frame_pixels(
            int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0), max_pixels,
        )
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_index is None:
            frame_index = frame_count // 2
        if frame_count > 0:
            frame_index = max(0, min(frame_index, frame_count - 1))

        frame = None
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok:
                frame = None
        if frame is None:
            # Seeking is not reliable for every codec/container; fall back to the first frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise ValueError('Video has no readable frames')
    finally:
        cap.release()

    # Mono cameras (e.g. Y800) are decoded to three identical BGR channels
    if frame.ndim == 3 and frame.shape[2] == 3 and np.array_equal(frame[..., 0], frame[..., 1]) \
            and np.array_equal(frame[..., 1], frame[..., 2]):
        frame = frame[..., 0]
    return _frame_to_png(frame, max_dim)


def _isolated_video_request(payload):
    from obs_run.file_check import IsolatedWorker, WorkerFailure

    with IsolatedWorker(timeout=VIDEO_READER_TIMEOUT) as worker:
        try:
            result = worker.request(payload)
        except WorkerFailure as failure:
            raise ValueError(f'Video reader {failure.reason}') from None
    if 'error' in result:
        raise ValueError(result['error'])
    return result


def render_video_frame_png_isolated(file_path: Path, max_dim: int = 512) -> bytes:
    """render_video_frame_png() in the isolated reader process (a reader crash raises ValueError)."""
    import base64

    from django.conf import settings

    result = _isolated_video_request({
        'action': 'video_thumbnail', 'path': str(file_path), 'max_dim': max_dim,
        'max_pixels': int(getattr(settings, 'THUMBNAIL_MAX_PIXELS', 50_000_000)),
    })
    return base64.b64decode(result['png'])


def read_video_frame_size(path):
    """(width, height) from the container metadata (in-process: use video_frame_size())."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError('Video file cannot be opened')
        return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()


def video_frame_size(path):
    """(width, height) of an AVI/MOV file, read in the isolated reader process; (-1, -1) if unknown."""
    try:
        width, height = _isolated_video_request({'action': 'video_size', 'path': str(path)})['size']
    except Exception:
        return -1, -1
    if width <= 0 or height <= 0:
        return -1, -1
    return width, height


def get_video_thumbnail_png(
    *,
    datafile_id: int,
    content_hash: str,
    file_path: Path,
    max_dim: int = 512,
) -> bytes:
    """Return cached PNG thumbnail for an AVI/MOV file, generating on cache miss."""
    return get_cached_thumbnail_png(
        datafile_id=datafile_id,
        content_hash=content_hash,
        file_path=file_path,
        max_dim=max_dim,
        render=render_video_frame_png_isolated,
    )
