"""
Image quality check: over-exposed and empty frames.

Reads the pixel data memory-friendly (FITS unscaled via memmap, strided sample of at most ~1 Mpx) and
computes the fraction of saturated pixels and the median level relative to full scale. The saturation level
comes from SATURATE/DATAMAX, else from BITPIX/BZERO (e.g. 65535 for unsigned 16 bit); for 8/16 bit
TIFF/JPG from the bit depth. Formats without readable pixel data here (CR2, SER, videos) stay unchecked.

Thresholds (settings): IMAGE_QUALITY_SATURATED_FRACTION (default 0.05) and IMAGE_QUALITY_MEDIAN_LEVEL
(default 0.9). Flats are bright but not saturated, so they stay below both.
"""
import math

import numpy as np
from astropy.io import fits
from django.conf import settings

OK = 'OK'
OVEREXPOSED = 'OE'
EMPTY = 'EM'
UNREADABLE = 'UR'
NOT_CHECKED = 'NC'
QUALITY_FLAG_CHOICES = (
    (OK, 'OK'),
    (OVEREXPOSED, 'Over-exposed'),
    (EMPTY, 'Empty / constant'),
    (UNREADABLE, 'Unreadable'),
    (NOT_CHECKED, 'Not checked'),
)
#   Flags that exclude a frame from plate solving, dark finder, heuristics and training data
BAD_FLAGS = (OVEREXPOSED, EMPTY, UNREADABLE)

SAMPLE_MAX_PIXELS = 1_000_000
CHECKED_FILE_TYPES = ('FITS', 'TIFF', 'JPG')


def _level_from_header(header):
    for key in ('SATURATE', 'DATAMAX'):
        try:
            value = float(header.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    bitpix = header.get('BITPIX')
    bzero = float(header.get('BZERO', 0) or 0)
    if bitpix == 8:
        return 255.0
    if bitpix == 16:
        return 65535.0 if bzero >= 32768 else 32767.0
    if bitpix == 32:
        return 4294967295.0 if bzero >= 2 ** 31 else 2147483647.0
    return None  # floating point data


def _subsample(data):
    h, w = data.shape[-2:]
    step = max(1, int(math.sqrt(h * w / SAMPLE_MAX_PIXELS)))
    if data.ndim == 3:
        data = data[0] if data.shape[0] <= 4 else data[..., 0]
    return np.asarray(data[::step, ::step], dtype=np.float64)


def read_sample(path, file_type):
    """(pixel sample in physical units, saturation level or None)."""
    if file_type == 'FITS':
        with fits.open(path, memmap=True, ignore_missing_end=True, do_not_scale_image_data=True) as hdul:
            hdu = next((h for h in hdul if h.data is not None and h.data.ndim >= 2), None)
            if hdu is None:
                raise ValueError('no image data')
            scale = float(hdu.header.get('BSCALE', 1.0) or 1.0)
            zero = float(hdu.header.get('BZERO', 0.0) or 0.0)
            return _subsample(hdu.data) * scale + zero, _level_from_header(hdu.header)
    from PIL import Image
    with Image.open(path) as img:
        bits = {'L': 8, 'P': 8, 'RGB': 8, 'RGBA': 8, 'I;16': 16, 'I;16B': 16}.get(img.mode)
        data = np.asarray(img)
    if data.ndim == 3:
        data = data.mean(axis=-1)
    return _subsample(data), (float(2 ** bits - 1) if bits else None)


def assess(sample, level):
    """(flag, saturated fraction or None, median level or None) for a pixel sample."""
    sample = np.nan_to_num(sample)
    if sample.size == 0:
        return EMPTY, None, None
    constant = float(sample.std()) < 1e-6
    if not level:
        return (EMPTY if constant else OK), None, None
    # Saturation first: a completely saturated frame is constant as well, but over-exposed, not empty
    saturated = round(float(np.mean(sample >= 0.98 * level)), 5)
    median_level = round(float(np.median(sample) / level), 5)
    limit_fraction = getattr(settings, 'IMAGE_QUALITY_SATURATED_FRACTION', 0.05)
    limit_median = getattr(settings, 'IMAGE_QUALITY_MEDIAN_LEVEL', 0.9)
    if saturated >= limit_fraction or median_level >= limit_median:
        return OVEREXPOSED, saturated, median_level
    return (EMPTY if constant else OK), saturated, median_level


def check_datafile(datafile):
    """(flag, saturated fraction, median level) for a DataFile, without saving."""
    file_type = (datafile.file_type or '').upper()
    if file_type not in CHECKED_FILE_TYPES:
        return NOT_CHECKED, None, None
    try:
        sample, level = read_sample(datafile.datafile, file_type)
    except Exception:
        return UNREADABLE, None, None
    return assess(sample, level)


def apply_quality(datafile, save=True):
    """Check and store the quality fields (keeps a manually set flag). Returns the flag."""
    if datafile.quality_flag_override:
        return datafile.quality_flag
    flag, saturated, median_level = check_datafile(datafile)
    datafile.quality_flag = flag
    datafile.saturated_fraction = saturated
    datafile.median_level = median_level
    if save:
        datafile.save(update_fields=['quality_flag', 'saturated_fraction', 'median_level'])
    return flag
