import numpy as np

from astropy.time import Time
from astropy.coordinates.angles import Angle


############################################################################


def extract_fits_header_info(header):
    """
        Read fits header info

        Parameters
        ----------
        header          : `astropy.io.fits.header` object
            FITS Header
    """
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
        data['obs_date'] = Time(
            header.get('hjd', 2400000),
            format='jd'
        ).iso

    #   Target
    data['objectname'] = header.get('OBJECT', '-')

    try:
        data['ra'] = float(header.get('OBJCTRA', 0.))
    except Exception:
        try:
            data['ra'] = Angle(header.get('OBJCTRA', 0.), unit='hour').degree
        except:
            data['ra'] = 0.

    try:
        data['dec'] = float(header.get('OBJCTDEC', 0.))
    except Exception:
        try:
            data['dec'] = Angle(header.get('OBJCTDEC', 0.), unit='degree').degree
        except:
            data['dec'] = 0.

    #   Telescope and instrument info
    data['instrument'] = header.get('INSTRUME', 'UK')
    data['telescope'] = header.get('TELESCOP', 'UK')
    data['exptime'] = np.round(header.get('EXPTIME', -1), 0)
    data['observer'] = header.get('OBSERVER', 'UK')
    data['imagetyp'] = header.get('IMAGETYP', 'UK')
    data['focal_length'] = header.get('FOCALLEN', -1)

    #   Image properties
    data['naxis1'] = header.get('NAXIS1', -1)
    data['naxis2'] = header.get('NAXIS2', -1)
    data['pixel_size'] = header.get('XPIXSZ', -1)

    #   Binning factors (robust to different header conventions)
    binx = header.get('XBINNING', None) or header.get('XBIN', None) or header.get('BINX', None)
    biny = header.get('YBINNING', None) or header.get('YBIN', None) or header.get('BINY', None)
    binning = header.get('BINNING', None)
    def _parse_int(v):
        try:
            return int(str(v).strip())
        except Exception:
            return None
    bx = _parse_int(binx)
    by = _parse_int(biny)
    if (bx is None or by is None) and binning is not None:
        # Accept formats like "2x2", "2 2", "2,2"
        import re
        parts = [p for p in re.split(r"[^0-9]+", str(binning)) if p]
        if len(parts) >= 2:
            bx = _parse_int(parts[0]) or 1
            by = _parse_int(parts[1]) or 1
    data['binning_x'] = bx or 1
    data['binning_y'] = by or 1

    #   Observing conditions
    data['air_mass'] = header.get('AIRMASS', -1)
    data['ambient_temperature'] = header.get('AOCAMBT', -1)
    data['dewpoint'] = header.get('AOCDEW', -1)
    data['pressure'] = header.get('AOCBAROM', -1)
    data['humidity'] = header.get('AOCHUM', -1)
    data['wind_speed'] = header.get('AOCWIND', -1)
    data['wind_direction'] = header.get('AOCWINDD', -1)

    # Camera parameters (for dark matching)
    # CCD temperature
    ccd_temp = header.get('CCD-TEMP', None) or header.get('SET-TEMP', None) or \
               header.get('CCDTEMP', None) or header.get('TEMPERAT', None)
    if ccd_temp is not None:
        try:
            data['ccd_temp'] = float(ccd_temp)
        except Exception:
            data['ccd_temp'] = -999
    else:
        data['ccd_temp'] = -999

    # Gain
    gain = header.get('GAIN', None) or header.get('ISO', None)
    if gain is not None:
        try:
            data['gain'] = float(gain)
        except Exception:
            data['gain'] = -1
    else:
        data['gain'] = -1

    # EGAIN 
    egain = header.get('EGAIN', None)
    if egain is not None:
        try:
            data['egain'] = float(egain)
        except Exception:
            data['egain'] = -1
    else:
        data['egain'] = -1

    # PEDESTAL
    pedestal = header.get('PEDESTAL', None)
    if pedestal is not None:
        try:
            data['pedestal'] = int(float(pedestal))
        except Exception:
            data['pedestal'] = -1
    else:
        data['pedestal'] = -1

    # Offset
    offset = header.get('OFFSET', None) or header.get('BLKLEVEL', None) or \
             header.get('BRIGHTNESS', None)
    if offset is not None:
        try:
            data['offset'] = int(float(offset))
        except Exception:
            data['offset'] = -1
    else:
        data['offset'] = -1

    # Readout mode
    readout_mode = header.get('READOUTM', None) or header.get('READMODE', None) or \
                   header.get('RDMODE', None)
    data['readout_mode'] = str(readout_mode).strip() if readout_mode else ''

    return data


############################################################################


def detect_instrument(naxis1, naxis2, pixel_um, binx, biny):
    """
    Infer instrument/camera name from geometry and pixel size.
    Accepts binned image sizes; will scale back to unbinned using binning factors.
    """
    try:
        bw = max(int(binx), 1)
        bh = max(int(biny), 1)
    except Exception:
        bw = 1
        bh = 1
    try:
        w = int(naxis1) * bw
        h = int(naxis2) * bh
    except Exception:
        w, h = -1, -1
    try:
        px = float(pixel_um)
    except Exception:
        px = -1.0

    catalog = [
        { 'name': 'QHY600M', 'px_um': 3.76, 'w': 9576, 'h': 6388, 'w_alt': 9600, 'h_alt': 6422 },
        { 'name': 'QHY268M', 'px_um': 3.76, 'w': 6252, 'h': 4176, 'w_alt': 6280, 'h_alt': 4210 },
        { 'name': 'ST8',     'px_um': 9.00, 'w': 1530, 'h': 1020 },
        { 'name': 'ST7',     'px_um': 9.00, 'w': 765,  'h': 510  },
        { 'name': 'STF-8300M','px_um': 5.40,'w': 3326, 'h': 2504 },
        { 'name': 'ST-i',    'px_um': 7.40, 'w': 648,  'h': 486  },
        { 'name': 'QHY485C', 'px_um': 2.90, 'w': 3864, 'h': 2180 },
        { 'name': 'Skyris 445C', 'px_um': 3.75, 'w': 1280, 'h': 960 },
        { 'name': 'ASI174MM', 'px_um': 5.86, 'w': 1936, 'h': 1216 },
        { 'name': 'ASI220MM', 'px_um': 4.00, 'w': 1920, 'h': 1080 },
        { 'name': 'ASI678MM', 'px_um': 2.00, 'w': 3840, 'h': 2160 },
    ]

    def close(a, b, tol=0.03):
        try:
            return abs(a - b) <= tol * max(a, b)
        except Exception:
            return False

    for item in catalog:
        if px > 0 and item['px_um'] > 0 and not close(px, item['px_um'], 0.15):
            pass
        targets = [(item['w'], item['h'])]
        if 'w_alt' in item and 'h_alt' in item:
            targets.append((item['w_alt'], item['h_alt']))
        for (tw, th) in targets:
            if (close(w, tw, 0.03) and close(h, th, 0.03)) or (close(w, th, 0.03) and close(h, tw, 0.03)):
                return item['name']
    return None


def analyze_fits(datafile):
    """
        Extract HEADER information from the FITS files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance
    """
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
    datafile.naxis1 = header_data.get('naxis1', 0.)
    datafile.naxis2 = header_data.get('naxis2', 0.)
    datafile.instrument = header_data.get('instrument', 'Unknown')
    datafile.telescope = header_data.get('telescope', 'Unknown')
    datafile.air_mass = header_data.get('air_mass', -1)
    datafile.ambient_temperature = header_data.get('ambient_temperature', -1)
    datafile.dewpoint = header_data.get('dewpoint', -1)
    datafile.pressure = header_data.get('pressure', -1)
    datafile.humidity = header_data.get('humidity', -1)
    datafile.wind_speed = header_data.get('wind_speed', -1)
    datafile.wind_direction = header_data.get('wind_direction', -1)
    datafile.focal_length = header_data.get('focal_length', -1)
    datafile.pixel_size = header_data.get('pixel_size', -1)

    # Camera parameters
    datafile.ccd_temp = header_data.get('ccd_temp', -999)
    datafile.gain = header_data.get('gain', -1)
    datafile.egain = header_data.get('egain', -1)
    datafile.pedestal = header_data.get('pedestal', -1)
    datafile.offset = header_data.get('offset', -1)
    datafile.readout_mode = header_data.get('readout_mode', '')
    datafile.binning_x = header_data.get('binning_x', 1)
    datafile.binning_y = header_data.get('binning_y', 1)

    #   Calculate chip size in mm
    if datafile.pixel_size in [0, -1] and datafile.focal_length in [0, -1]:
        pixel_size_mm = datafile.pixel_size / 1000
        d = datafile.naxis1 * pixel_size_mm
        h = datafile.naxis2 * pixel_size_mm

        #   Calculate field of view
        double_focal_len = 2 * datafile.focal_length
        fov_x = 2 * np.arctan(d / double_focal_len)
        fov_y = 2 * np.arctan(h / double_focal_len)

        #   Convert to degree
        two_pi = 2. * np.pi
        datafile.fov_x = fov_x * 360. / two_pi
        datafile.fov_y = fov_y * 360. / two_pi

    #   Image type definitions
    img_types = {
        'Bias Frame': 'BI',
        'Bias': 'BI',
        'BIAS': 'BI',
        'Dark Frame': 'DA',
        'Dark': 'DA',
        'DARK': 'DA',
        'Flat Field': 'FL',
        'Flat': 'FL',
        'FLAT': 'FL',
        'Light Frame': 'LI',
        'Light': 'LI',
        'LIGHT': 'LI',
    }

    #   Sanitize image type
    img_type = header_data.get('imagetyp', 'UK')
    for key, value in img_types.items():
        if key == img_type:
            datafile.exposure_type = value
            break
    else:
        datafile.exposure_type = 'UK'

    #   Set object name
    if datafile.exposure_type in ['UK', 'LI']:
        datafile.main_target = header_data.get('objectname', '-')
        datafile.header_target_name = header_data.get('objectname', '-')
    else:
        datafile.main_target = '-'
        datafile.header_target_name = '-'

    # Infer instrument from header/geometry if header instrument is generic or missing
    try:
        header_instr = header_data.get('instrument', '') or ''
    except Exception:
        header_instr = ''

    inferred = detect_instrument(
        header_data.get('naxis1', -1),
        header_data.get('naxis2', -1),
        header_data.get('pixel_size', -1),
        header_data.get('binning_x', 1),
        header_data.get('binning_y', 1),
    )

    # Prefer inferred instrument when header is generic or missing
    generic_markers = ['unknown', 'uk', 'qhyccd-cameras-capture', 'asi camera (1)']
    assign_inferred = False
    if inferred:
        if not header_instr:
            assign_inferred = True
        else:
            lower = header_instr.strip().lower()
            if any(g in lower for g in generic_markers):
                assign_inferred = True
    if assign_inferred:
        datafile.instrument = inferred

    datafile.save()
