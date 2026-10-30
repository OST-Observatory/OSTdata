"""Tests for AVI/MOV thumbnail generation and API endpoint."""
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.file_check import IsolatedWorker, WorkerFailure
from obs_run.models import DataFile, ObservationRun
from obs_run.video_thumbnails import (
    get_video_thumbnail_png,
    is_video_path,
    render_video_frame_png,
    video_frame_size,
)


def _write_avi(path: Path, frames: int = 5, color: bool = False) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48), isColor=color)
    for i in range(frames):
        shape = (48, 64, 3) if color else (48, 64)
        writer.write(np.full(shape, 40 * i, dtype=np.uint8))
    writer.release()


class VideoThumbnailHelpersTest(APITestCase):
    def test_is_video_path_by_type_and_suffix(self):
        self.assertTrue(is_video_path('AVI', Path('/data/foo.bar')))
        self.assertTrue(is_video_path('', Path('/data/foo.AVI')))
        self.assertTrue(is_video_path('MOV', Path('/data/foo.mov')))
        self.assertFalse(is_video_path('SER', Path('/data/foo.ser')))

    def test_render_mono_avi_returns_grayscale_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'clip.avi'
            _write_avi(path, color=False)
            png = render_video_frame_png(path, max_dim=32)

        img = Image.open(BytesIO(png))
        self.assertEqual(img.format, 'PNG')
        self.assertEqual(img.mode, 'L')
        self.assertLessEqual(max(img.size), 32)

    def test_render_color_avi_returns_rgb_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'clip.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48))
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            frame[:, :32] = (255, 0, 0)  # blue half (BGR)
            frame[:, 32:] = (0, 0, 255)  # red half
            for _ in range(3):
                writer.write(frame)
            writer.release()
            png = render_video_frame_png(path, max_dim=64)

        img = Image.open(BytesIO(png))
        self.assertEqual(img.mode, 'RGB')
        r, _g, b = img.getpixel((60, 24))
        self.assertGreater(r, b)  # right half stays red after BGR -> RGB

    def test_render_invalid_file_raises(self):
        with tempfile.NamedTemporaryFile(suffix='.avi') as tmp:
            tmp.write(b'not a video')
            tmp.flush()
            with self.assertRaises(ValueError):
                render_video_frame_png(Path(tmp.name))

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.video_thumbnails.render_video_frame_png_isolated')
    def test_get_video_thumbnail_png_uses_cache(self, render_mock):
        render_mock.return_value = b'\x89PNGcached'
        with tempfile.NamedTemporaryFile(suffix='.avi', delete=False) as tmp:
            path = Path(tmp.name)
            path.write_bytes(b'avi-data')

        for _ in range(2):
            png = get_video_thumbnail_png(datafile_id=7, content_hash='abc', file_path=path, max_dim=128)
            self.assertEqual(png, b'\x89PNGcached')
        render_mock.assert_called_once()


class VideoThumbnailApiTest(APITestCase):
    def setUp(self):
        self.obs_run = ObservationRun.objects.create(name='2024-01-01_video', is_public=True)
        # Path jail requires files under DATA_DIRECTORY
        root = Path(settings.DATA_DIRECTORY)
        root.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = tempfile.mkdtemp(dir=root)
        self.avi_path = Path(self.tmp_dir) / 'clip.avi'
        _write_avi(self.avi_path)
        self.df = DataFile.objects.create(
            observation_run=self.obs_run,
            datafile=str(self.avi_path),
            file_type='AVI',
            content_hash='hash-avi',
        )
        self.url = f'/api/runs/datafiles/{self.df.pk}/thumbnail/'

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    def test_public_avi_thumbnail_returns_png(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertTrue(resp.content.startswith(b'\x89PNG'))

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.api.views.get_video_thumbnail_png', side_effect=ValueError('bad avi'))
    def test_avi_thumbnail_generation_error(self, _thumb_mock):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp(), THUMBNAIL_MAX_SOURCE_BYTES=1)
    def test_avi_is_exempt_from_source_size_limit(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp(), THUMBNAIL_MAX_PIXELS=100)
    def test_avi_frame_above_pixel_limit_is_rejected(self):
        resp = self.client.get(self.url)  # 64x48 frame > 100 pixels
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class IsolatedVideoReaderTest(APITestCase):
    """OpenCV crashes on some videos (SIGABRT/SIGSEGV): only the isolated reader process may die."""

    def test_frame_size_from_the_reader_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'clip.avi'
            _write_avi(path)
            self.assertEqual(video_frame_size(path), (64, 48))
            self.assertEqual(video_frame_size(Path(tmp) / 'missing.avi'), (-1, -1))

    def test_reader_crash_gives_no_size_instead_of_killing_the_caller(self):
        with patch.object(IsolatedWorker, 'request', side_effect=WorkerFailure('crashed (exit code -6)')):
            self.assertEqual(video_frame_size('/tmp/AllSky.avi'), (-1, -1))

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    def test_reader_crash_gives_an_error_response(self):
        root = Path(settings.DATA_DIRECTORY)
        root.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(dir=root)) / 'AllSky.avi'
        _write_avi(path)
        run = ObservationRun.objects.create(name='2023-05-26', is_public=True)
        datafile = DataFile.objects.create(observation_run=run, datafile=str(path), file_type='AVI', content_hash='crash')
        with patch.object(IsolatedWorker, 'request', side_effect=WorkerFailure('crashed (exit code -11)')):
            resp = self.client.get(f'/api/runs/datafiles/{datafile.pk}/thumbnail/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
