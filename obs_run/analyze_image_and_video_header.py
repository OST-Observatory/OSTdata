from astropy.time import Time

from datetime import datetime
import os

import pytz

import exifread

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
    except:
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
    except:
        exptime = 0.

    #   Image size
    try:
        naxis1 = float(tags['EXIF ExifImageWidth'].values[0])
    except:
        try:
            naxis1 = float(tags['Image ImageWidth'].values[0])
        except:
            naxis1 = -1
    try:
        naxis2 = float(tags['EXIF ExifImageLength'].values[0])
    except:
        try:
            naxis2 = float(tags['Image ImageLength'].values[0])
        except:
            naxis2 = -1

    #   Set values
    datafile.exposure_type = 'UK'
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
        obs_date = t.to_datetime().strftime("%Y-%m-%d %H:%M:%S")
        jd = t.jd

    datafile.exposure_type = 'UK'
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = -1.
    datafile.naxis1 = -1
    datafile.naxis2 = -1

    datafile.save()

############################################################################

def analyze_ser(datafile):
    '''
        Extract HEADER informations from .ser files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance
    '''
    #   Get .ser-Header only; avoid dynamic-range probing that reads frames
    parser = SERParser(
        datafile.datafile,
        SER_16bit_shift_correction=False,
    )
    header = parser.header

    #   Get observation time and date (fallbacks)
    dt = header.get('DateTime_UTC_Decoded') or header.get('DateTime_Decoded')
    if dt is not None:
        obs_date = dt.strftime("%Y-%m-%d %H:%M:%S")
        jd = Time(obs_date, format='iso', scale='utc').jd
    else:
        obs_date = '2000-01-01 00:00:00'
        jd = Time(obs_date, format='iso', scale='utc').jd

    #   Image size
    naxis1 = float(header['ImageWidth'])
    naxis2 = float(header['ImageHeight'])

    #   Set values
    datafile.exposure_type = 'UK'
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = -1.
    datafile.naxis1 = naxis1
    datafile.naxis2 = naxis2

    datafile.save()
