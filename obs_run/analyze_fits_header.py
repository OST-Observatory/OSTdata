import numpy as np

from astropy.time import Time
from astropy.coordinates.angles import Angle

############################################################################

def extract_fits_header_info(header):
    '''
        Read fits header info

        Parameters
        ----------
        header          : `astropy.io.fits.header` object
            FITS Header
    '''
    #   Initialize data array
    data = {}

    #   HJD
    if 'HJD' in header:
        data['hjd'] = header['HJD']
    elif 'BJD' in header:
        data['hjd'] = header['BJD']
    elif 'MJD' in header:
        data['hjd'] = Time(header.get('MJD', 0.0), format='mjd', scale='utc').jd
    elif 'DATE-OBS' in header:
        date = header.get('DATE-OBS', '2000-00-00')
        if 'T' not in date:
            if 'UT' in header:
                ut = header.get('UT', '00:00:00.0')
                data['hjd'] = Time(date + 'T' + ut, format='fits').jd
        else:
            data['hjd'] = Time(
                header.get('DATE-OBS', '2000-00-00T00:00:00.0Z'),
                format='fits'
            ).jd
    else:
        data['hjd'] = 2400000

    #   Obs. date
    if 'DATE-OBS' in header:
        date = header.get('DATE-OBS', '2000-00-00')
        data['obs_date'] = date.replace('T', ' ')
    else:
        data['obs_date'] =  Time(
            header.get('hjd', 2400000),
            format='jd'
        ).iso

    #   Target
    data['objectname'] = header.get('OBJECT', '')

    try:
        data['ra'] = float(header.get('OBJCTRA', 0.))
    except Exception:
        data['ra'] = Angle(header.get('OBJCTRA', 0.), unit='hour').degree

    try:
        data['dec'] = float(header.get('OBJCTDEC', 0.))
    except Exception:
        data['dec'] = Angle(header.get('OBJCTDEC', 0.), unit='degree').degree

    #   Telescope and instrument info
    data['instrument'] = header.get('INSTRUME', 'UK')
    data['telescope'] = header.get('TELESCOP', 'UK')
    data['exptime'] = np.round(header.get('EXPTIME', -1), 0)
    data['observer'] = header.get('OBSERVER', 'UK')
    data['imagetyp'] = header.get('IMAGETYP', 'UK')

    #   Image properties
    data['naxis1'] = header.get('NAXIS1', -1)
    data['naxis2'] = header.get('NAXIS2', -1)

    return data

############################################################################

def analyze_fits(datafile):
    '''
        Extract HEADER informations from the FITS files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance
    '''
    #   Get Header
    header = datafile.get_fits_header()

    #   Extract info from Header
    header_data = extract_fits_header_info(header)

    #   Set basic values
    datafile.hjd = header_data.get('hjd', 2400000.)
    datafile.obs_date = header_data.get('obs_date', '2000-00-00')
    datafile.exptime = header_data.get('exptime', 0.)
    datafile.ra = header_data.get('ra', -1)
    datafile.dec = header_data.get('dec', -1)
    datafile.main_target = header_data.get('objectname', 'Unknown')
    datafile.naxis1 = header_data.get('naxis1', 0.)
    datafile.naxis2 = header_data.get('naxis2', 0.)
    datafile.main_target = header_data.get('objectname', 'Unknown')

    #   Image type definitions
    img_types = {
        'Bias Frame':'BI',
        'Bias':'BI',
        'BIAS':'BI',
        'Dark Frame':'DA',
        'Dark':'DA',
        'DARK':'DA',
        'Flat Field':'FL',
        'Flat':'FL',
        'FLAT':'FL',
        'Light Frame':'LI',
        'Light':'LI',
        'LIGHT':'LI',
        }

    #   Sanitize image type
    img_type = header_data.get('imagetyp', 'UK')
    for key, value in img_types.items():
        if key == img_type:
            datafile.exposure_type = value
            break
    else:
        datafile.exposure_type = 'UK'

    datafile.save()