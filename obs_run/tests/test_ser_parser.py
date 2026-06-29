"""Tests for SER parser (LUCAM + INDI variants)."""
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from obs_run.ser_parser import (
    SERParser,
    infer_frame_count_from_size,
    _normalize_file_id,
    _ser_pixel_endian,
)

SUN_WHITE_SER = (
    Path(__file__).resolve().parents[2]
    / 'test_data'
    / '2022-05-08'
    / 'sun_white_20220508.ser'
)


class SerParserHelpersTest(SimpleTestCase):
    def test_normalize_file_id_strips_padding(self):
        self.assertEqual(_normalize_file_id(b'INDI-RECORDER\x00'), 'INDI-RECORDER')

    def test_ser_pixel_endian_indi_big_endian_default(self):
        self.assertEqual(_ser_pixel_endian('INDI-RECORDER', 0), '>')
        self.assertEqual(_ser_pixel_endian('INDI-RECORDER', 1), '<')

    def test_ser_pixel_endian_lucam_legacy_defaults_to_little(self):
        self.assertEqual(_ser_pixel_endian('LUCAM-RECORDER', 0), '<')


@unittest.skipUnless(SUN_WHITE_SER.is_file(), 'sun_white SER fixture missing')
class SunWhiteSerIntegrationTest(SimpleTestCase):
    def test_indi_recorder_parses_without_warning(self):
        parser = SERParser(str(SUN_WHITE_SER))
        try:
            self.assertIsNone(parser.warn_message)
            self.assertEqual(parser.header['FileId'], 'INDI-RECORDER')
            self.assertEqual(parser.frame_count, 4)
            self.assertEqual(str(parser.PixelDepthPerPlane), '>u2')
            frame = parser.read_frame(0)
            self.assertEqual(frame.shape, (4176, 6248, 3))
            self.assertGreater(int(frame.max()), 10000)
        finally:
            parser.release()

    def test_thumbnail_frame_index_middle(self):
        parser = SERParser(str(SUN_WHITE_SER))
        try:
            mid = parser.frame_count // 2
            frame = parser.read_frame(mid)
            self.assertEqual(frame.ndim, 3)
        finally:
            parser.release()


class SerParserFrameCountInferenceTest(SimpleTestCase):
    def setUp(self):
        if not SUN_WHITE_SER.is_file():
            self.skipTest('sun_white SER fixture missing')
        self.tmp_dir = tempfile.mkdtemp()
        self.copy_path = Path(self.tmp_dir) / 'zeroed_count.ser'
        shutil.copy(SUN_WHITE_SER, self.copy_path)
        with open(self.copy_path, 'r+b') as fid:
            fid.seek(14 + 6 * 4)
            fid.write(struct.pack('<i', 0))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_infer_frame_count_from_size(self):
        parser = SERParser(str(self.copy_path))
        try:
            self.assertEqual(parser.frame_count, 4)
            self.assertTrue(parser.header.get('FrameCountInferred'))
        finally:
            parser.release()

    def test_infer_frame_count_helper_matches_file(self):
        parser = SERParser(str(SUN_WHITE_SER))
        try:
            inferred = infer_frame_count_from_size(str(SUN_WHITE_SER), parser.frame_size)
            self.assertEqual(inferred, 4)
        finally:
            parser.release()
