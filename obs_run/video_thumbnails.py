"""AVI/MOV video frame extraction (OpenCV/FFmpeg) and cached PNG thumbnails."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from obs_run.ser_thumbnails import _frame_to_png, check_frame_pixels, get_cached_thumbnail_png

VIDEO_SUFFIXES = ('.avi', '.mov')


def is_video_path(file_type: str | None, file_path: Path) -> bool:
    ft = (file_type or '').upper()
    return ft in ('AVI', 'MOV') or file_path.suffix.lower() in VIDEO_SUFFIXES


def render_video_frame_png(file_path: Path, max_dim: int = 512, frame_index: int | None = None) -> bytes:
    """Extract one frame (middle of the video by default) and return PNG bytes."""
    import cv2

    cap = cv2.VideoCapture(str(file_path))
    try:
        if not cap.isOpened():
            raise ValueError('Video file cannot be opened')
        check_frame_pixels(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0))
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
        render=render_video_frame_png,
    )
