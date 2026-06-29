"""Tests for SER thumbnail generation and API endpoint."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from obs_run.models import DataFile, ObservationRun
from obs_run.ser_thumbnails import get_ser_thumbnail_png, is_ser_path, render_ser_frame_png

User = get_user_model()


class SerThumbnailHelpersTest(APITestCase):
    def test_is_ser_path_by_type_and_suffix(self):
        self.assertTrue(is_ser_path('SER', Path('/data/foo.bar')))
        self.assertTrue(is_ser_path('', Path('/data/foo.ser')))
        self.assertFalse(is_ser_path('FITS', Path('/data/foo.fits')))

    @patch('obs_run.ser_parser.SERParser')
    def test_render_ser_frame_png_grayscale(self, parser_cls):
        parser = MagicMock()
        parser.frame_count = 10
        parser.read_frame.return_value = np.arange(100, dtype=np.uint16).reshape(10, 10)
        parser_cls.return_value = parser

        with tempfile.NamedTemporaryFile(suffix='.ser') as tmp:
            png = render_ser_frame_png(Path(tmp.name), max_dim=64, frame_index=5)

        self.assertTrue(png.startswith(b'\x89PNG'))
        parser.read_frame.assert_called_once_with(5)
        parser.release.assert_called_once()

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.ser_thumbnails.render_ser_frame_png')
    def test_get_ser_thumbnail_png_uses_cache(self, render_mock):
        render_mock.return_value = b'\x89PNGcached'

        with tempfile.NamedTemporaryFile(suffix='.ser', delete=False) as tmp:
            path = Path(tmp.name)
            path.write_bytes(b'ser-data')

        png1 = get_ser_thumbnail_png(
            datafile_id=42,
            content_hash='abc',
            file_path=path,
            max_dim=128,
        )
        png2 = get_ser_thumbnail_png(
            datafile_id=42,
            content_hash='abc',
            file_path=path,
            max_dim=128,
        )

        self.assertEqual(png1, b'\x89PNGcached')
        self.assertEqual(png2, b'\x89PNGcached')
        render_mock.assert_called_once()


class SerThumbnailApiTest(APITestCase):
    def setUp(self):
        self.run = ObservationRun.objects.create(name='2024-01-01_test', is_public=True)
        self.tmp_dir = tempfile.mkdtemp()
        self.ser_path = Path(self.tmp_dir) / 'clip.ser'
        self.ser_path.write_bytes(b'placeholder')
        self.df = DataFile.objects.create(
            observation_run=self.run,
            datafile=str(self.ser_path),
            file_type='SER',
            content_hash='hash123',
        )
        self.url = f'/api/runs/datafiles/{self.df.pk}/thumbnail/'

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.api.views.get_ser_thumbnail_png')
    def test_public_ser_thumbnail_returns_png(self, thumb_mock):
        thumb_mock.return_value = b'\x89PNGtest'

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertEqual(resp.content, b'\x89PNGtest')
        thumb_mock.assert_called_once()

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.api.views.get_ser_thumbnail_png', side_effect=ValueError('bad ser'))
    def test_ser_thumbnail_generation_error(self, _thumb_mock):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(SER_THUMBNAIL_CACHE_DIR=tempfile.mkdtemp())
    @patch('obs_run.api.views.get_ser_thumbnail_png')
    def test_private_ser_thumbnail_requires_auth(self, thumb_mock):
        thumb_mock.return_value = b'\x89PNGtest'
        private_run = ObservationRun.objects.create(name='2024-01-02_priv', is_public=False)
        ser = Path(self.tmp_dir) / 'private.ser'
        ser.write_bytes(b'x')
        df = DataFile.objects.create(
            observation_run=private_run,
            datafile=str(ser),
            file_type='SER',
        )

        anon = self.client.get(f'/api/runs/datafiles/{df.pk}/thumbnail/')
        self.assertEqual(anon.status_code, status.HTTP_404_NOT_FOUND)

        user = User.objects.create_user(username='reader', password='pass')
        private_run.readonly_users.add(user)
        self.client.force_login(user)
        ok = self.client.get(f'/api/runs/datafiles/{df.pk}/thumbnail/')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
