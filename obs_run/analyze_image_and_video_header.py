import os
from datetime import datetime

import exifread
import pytz
from astropy.time import Time

from obs_run.exposure_type import format_default_exposure_type
from obs_run.utils import should_allow_auto_update

from .ser_parser import SERParser

############################################################################

def analyze_image(datafile):
    '''
        Extract EXIF informations from .jpg, .cr2, ... files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance
    '''
    #   Open file
    f = open(datafile.datafile, 'rb')

    #   Get EXIF data
    tags = exifread.process_file(f)

    #   Get observation time and date
    try:
        obs_date = tags['EXIF DateTimeOriginal'].values
    except Exception:
        obs_date = '2000:01:01 01:00:00'

    #   Local timezone
    local = pytz.timezone("Europe/Berlin")

    #   Convert date and time to datetime object and then to UTC
    naive = datetime.strptime(obs_date, "%Y:%m:%d %H:%M:%S")
    local_dt = local.localize(naive, is_dst=None)
    utc_dt = local_dt.astimezone(pytz.utc)
    obs_date = utc_dt.strftime("%Y-%m-%d %H:%M:%S")

    #   Calculate JD
    jd = Time(obs_date, format='iso', scale='utc').jd

    #   Exposure time
    try:
        exptime = float(tags['EXIF ExposureTime'].values[0])
    except Exception:
        exptime = 0.

    #   Image size
    try:
        naxis1 = float(tags['EXIF ExifImageWidth'].values[0])
    except Exception:
        try:
            naxis1 = float(tags['Image ImageWidth'].values[0])
        except Exception:
            naxis1 = -1
    try:
        naxis2 = float(tags['EXIF ExifImageLength'].values[0])
    except Exception:
        try:
            naxis2 = float(tags['Image ImageLength'].values[0])
        except Exception:
            naxis2 = -1

    #   Set values (check override flag for exposure_type)
    if should_allow_auto_update(datafile, 'exposure_type'):
        datafile.exposure_type = format_default_exposure_type(datafile.file_type)
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = exptime
    datafile.naxis1 = naxis1
    datafile.naxis2 = naxis2

    datafile.save()

############################################################################

def analyze_video(datafile):
    '''
        Minimal metadata extraction for generic video files (.avi, .mov).
        Uses filesystem modification time as observation timestamp.
    '''
    try:
        mtime = os.path.getmtime(datafile.datafile)
    except Exception:
        # Fallback to a constant default if mtime can't be read
        obs_date = '2000-01-01 00:00:00'
        jd = Time(obs_date, format='iso', scale='utc').jd
    else:
        t = Time(mtime, format='unix', scale='utc')
        dt = t.to_datetime()
        obs_date = getattr(dt, 'strftime', lambda *_a, **_k: str(dt))("%Y-%m-%d %H:%M:%S")
        jd = t.jd

    if should_allow_auto_update(datafile, 'exposure_type'):
        datafile.exposure_type = format_default_exposure_type(datafile.file_type)
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = -1.
    #   Frame size (container metadata only, no decoding) for the instrument detection
    datafile.naxis1, datafile.naxis2 = video_frame_size(datafile.datafile)

    datafile.save()


def video_frame_size(path):
    """(width, height) of an AVI/MOV file from its container metadata; (-1, -1) if unknown."""
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        try:
            if not cap.isOpened():
                return -1, -1
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            cap.release()
    except Exception:
        return -1, -1
    if width <= 0 or height <= 0:
        return -1, -1
    return width, height

############################################################################

def analyze_ser(datafile):
    '''
        Extract HEADER informations from .ser files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance
    '''
    header = read_ser_header(datafile.datafile)

    #   Get observation time and date (fallbacks)
    dt = header.get('DateTime_UTC_Decoded') or header.get('DateTime_Decoded')
    strftime = getattr(dt, 'strftime', None)
    if callable(strftime):
        obs_date = strftime("%Y-%m-%d %H:%M:%S")
        jd = Time(obs_date, format='iso', scale='utc').jd
    else:
        obs_date = '2000-01-01 00:00:00'
        jd = Time(obs_date, format='iso', scale='utc').jd

    #   Image size
    naxis1 = float(header['ImageWidth'])
    naxis2 = float(header['ImageHeight'])

    #   Set values (check override flag for exposure_type)
    if should_allow_auto_update(datafile, 'exposure_type'):
        datafile.exposure_type = format_default_exposure_type(datafile.file_type)
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = -1.
    datafile.naxis1 = naxis1
    datafile.naxis2 = naxis2

    #   Camera: name from the header (written by most capture tools) and sensor type from
    #   ColorID; save() resolves the canonical instrument name from both
    camera = ser_camera_name(header.get('Instrument'))
    if camera and should_allow_auto_update(datafile, 'instrument'):
        datafile.instrument = camera[:50]
    datafile.color_sensor = ser_color_sensor(header.get('ColorID'))

    datafile.save()


def read_ser_header(path):
    """SER header only (no dynamic-range probing that reads frames); closes the file."""
    parser = SERParser(str(path), SER_16bit_shift_correction=False)
    try:
        return parser.header
    finally:
        parser.release()


def ser_camera_name(value):
    """Instrument field of a SER header (40 bytes, NUL/space padded) as clean string."""
    if not value:
        return ''
    if isinstance(value, (bytes, bytearray)):
        value = value.decode('latin1')
    return str(value).replace('\x00', ' ').strip()


def ser_color_sensor(color_id):
    """SER ColorID -> True (Bayer/RGB), False (mono), None (unknown value)."""
    if color_id == 0:
        return False
    if isinstance(color_id, int) and (8 <= color_id <= 19 or color_id in (100, 101)):
        return True
    return None
