from astropy.time import Time

from datetime import datetime

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
    obs_date = tags['EXIF DateTimeOriginal'].values

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
    exptime = float(tags['EXIF ExposureTime'].values[0])

    #   Image size
    naxis1 = float(tags['EXIF ExifImageWidth'].values[0])
    naxis2 = float(tags['EXIF ExifImageLength'].values[0])

    #   Set values
    datafile.exposure_type = 'UK'
    datafile.hjd = jd
    datafile.obs_date = obs_date
    datafile.exptime = exptime
    datafile.naxis1 = naxis1
    datafile.naxis2 = naxis2

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
    #   Get .ser-Header
    header = SERParser(
        datafile.datafile,
        SER_16bit_shift_correction=True,
        ).header

    #   Get observation time and date
    obs_date = header['DateTime_UTC_Decoded'].strftime("%Y-%m-%d %H:%M:%S")

    #   Calculate JD
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
