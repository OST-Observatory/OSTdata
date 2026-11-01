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
FFMPEG_TIMEOUT = 60


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


def ffmpeg_available() -> bool:
    import shutil

    return bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def ffprobe_info(path):
    """{'width', 'height', 'duration'} of the first video stream via ffprobe; raises if unreadable."""
    import json
    import subprocess

    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
         'stream=width,height:format=duration', '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=FFMPEG_TIMEOUT,
    )
    data = json.loads(result.stdout or '{}')
    streams = data.get('streams') or []
    if result.returncode != 0 or not streams:
        raise ValueError((result.stderr or 'no video stream').strip()[:200])
    try:
        duration = float((data.get('format') or {}).get('duration'))
    except (TypeError, ValueError):
        duration = None
    return {'width': int(streams[0].get('width') or 0), 'height': int(streams[0].get('height') or 0),
            'duration': duration}


def render_video_frame_png_ffmpeg(file_path: Path, max_dim: int = 512, max_pixels: int | None = None) -> bytes:
    """
    Middle frame via the ffmpeg command line (fallback for videos OpenCV's bundled FFmpeg cannot read,
    e.g. some uncompressed all-sky camera AVIs). ffmpeg is a separate process: a crash cannot hit us.
    """
    import subprocess
    from io import BytesIO

    from PIL import Image

    info = ffprobe_info(file_path)
    check_frame_pixels(info['width'], info['height'], max_pixels)
    seek = ['-ss', f"{info['duration'] / 2:.3f}"] if info['duration'] else []
    result = subprocess.run(
        ['ffmpeg', '-nostdin', '-v', 'error', *seek, '-i', str(file_path), '-frames:v', '1',
         '-f', 'image2pipe', '-c:v', 'png', '-'],
        capture_output=True, timeout=FFMPEG_TIMEOUT,
    )
    if result.returncode != 0 or not result.stdout:
        raise ValueError((result.stderr or b'no frame').decode('utf-8', 'replace').strip()[:200])
    with Image.open(BytesIO(result.stdout)) as img:
        frame = np.asarray(img.convert('L') if img.mode in ('L', 'LA', 'I', 'I;16', 'P') else img.convert('RGB'))
    if frame.ndim == 3:
        if np.array_equal(frame[..., 0], frame[..., 1]) and np.array_equal(frame[..., 1], frame[..., 2]):
            frame = frame[..., 0]
        else:
            frame = frame[..., ::-1]  # _frame_to_png expects OpenCV's BGR order
    return _frame_to_png(frame, max_dim)


def render_video_frame_png_isolated(file_path: Path, max_dim: int = 512) -> bytes:
    """
    render_video_frame_png() in the isolated reader process; if OpenCV fails (crash, unknown codec),
    the ffmpeg command line is tried. Raises ValueError if neither gives a frame.
    """
    import base64

    from django.conf import settings

    max_pixels = int(getattr(settings, 'THUMBNAIL_MAX_PIXELS', 50_000_000))
    try:
        result = _isolated_video_request({
            'action': 'video_thumbnail', 'path': str(file_path), 'max_dim': max_dim, 'max_pixels': max_pixels,
        })
        return base64.b64decode(result['png'])
    except ValueError as opencv_error:
        if not ffmpeg_available():
            raise
        try:
            return render_video_frame_png_ffmpeg(file_path, max_dim, max_pixels)
        except Exception as ffmpeg_error:
            raise ValueError(f'OpenCV: {opencv_error}; ffmpeg: {ffmpeg_error}') from None


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
    """
    (width, height) of an AVI/MOV file, read in the isolated reader process (ffprobe if OpenCV fails);
    (-1, -1) if unknown.
    """
    try:
        width, height = _isolated_video_request({'action': 'video_size', 'path': str(path)})['size']
    except Exception:
        try:
            info = ffprobe_info(path) if ffmpeg_available() else None
        except Exception:
            info = None
        if info is None:
            return -1, -1
        width, height = info['width'], info['height']
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
