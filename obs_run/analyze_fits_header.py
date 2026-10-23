import logging
import math

import numpy as np
from astropy.coordinates.angles import Angle
from astropy.time import Time

from obs_run.utils import INSTRUMENT_CATALOG, normalize_instrument, should_allow_auto_update

logger = logging.getLogger(__name__)


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
        except Exception:
            data['ra'] = 0.

    try:
        data['dec'] = float(header.get('OBJCTDEC', 0.))
    except Exception:
        try:
            data['dec'] = Angle(header.get('OBJCTDEC', 0.), unit='degree').degree
        except Exception:
            data['dec'] = 0.

    #   Telescope and instrument info
    data['instrument'] = header.get('INSTRUME', 'UK')
    data['telescope'] = header.get('TELESCOP', 'UK')
    
    # Exposure time - try multiple header keys and preserve decimal precision
    exptime = header.get('EXPTIME', None) or header.get('EXPOSURE', None) or header.get('EXPOSUR', None)
    if exptime is not None:
        try:
            exptime_val = float(exptime)
            # Only round if value is >= 10 second (preserve precision for sub-second exposures)
            if exptime_val >= 10.0:
                data['exptime'] = np.round(exptime_val, 0)
            else:
                # Preserve decimal precision for sub-second exposures (e.g., 0.1, 0.5)
                data['exptime'] = exptime_val
        except (ValueError, TypeError):
            data['exptime'] = -1
    else:
        data['exptime'] = -1
    
    data['observer'] = header.get('OBSERVER', 'UK')
    data['imagetyp'] = header.get('IMAGETYP', 'UK')
    
    # Focal length - try multiple header keys
    focal_length = header.get('FOCALLEN', None) or header.get('FOCAL', None) or header.get('FOCLEN', None)
    if focal_length is not None:
        try:
            data['focal_length'] = float(focal_length)
        except (ValueError, TypeError):
            data['focal_length'] = -1
    else:
        data['focal_length'] = -1

    #   Image properties
    data['naxis1'] = header.get('NAXIS1', -1)
    data['naxis2'] = header.get('NAXIS2', -1)
    
    # Pixel size - try multiple header keys (XPIXSZ is in microns)
    pixel_size = header.get('XPIXSZ', None) or header.get('XPIXSIZE', None) or header.get('PIXSIZE', None) or header.get('PIXSZ', None)
    if pixel_size is not None:
        try:
            pixel_size_val = float(pixel_size)
            # If pixel size is very large (> 100), it might be in mm instead of microns
            if pixel_size_val > 100:
                pixel_size_val = pixel_size_val * 1000.0  # Convert mm to microns
            data['pixel_size'] = pixel_size_val
        except (ValueError, TypeError):
            data['pixel_size'] = -1
    else:
        data['pixel_size'] = -1

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

    data['color_sensor'] = fits_color_sensor(header)

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


def fits_color_sensor(header):
    """
    Sensor type from a FITS header: a Bayer pattern keyword marks a one-shot-color camera (True).
    Its absence does not prove a mono sensor (not every capture software writes it): None.
    """
    bayer = header.get('BAYERPAT', None) or header.get('COLORTYP', None)
    return True if bayer is not None and str(bayer).strip() else None


def detect_instruments(naxis1, naxis2, pixel_um, binx, biny, color=None):
    """
    Infer all possible instrument/camera names from geometry and pixel size.
    Accepts binned image sizes; will scale back to unbinned using binning factors.
    color (True/False/None) narrows the matches to color or mono sensors; if no match has the
    given type (e.g. a color camera recording in mono mode), the geometry matches are kept.
    
    Returns:
        List of matching instrument names (may be empty or contain multiple matches)
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
        px_header = float(pixel_um)
    except Exception:
        px_header = -1.0
    # XPIXSZ is normally the binned pixel size (N.I.N.A., MaxIm); some software writes the
    # unbinned size. Accept both conventions.
    px_candidates = [px_header / bw, px_header] if px_header > 0 else []

    catalog = INSTRUMENT_CATALOG

    def close(a, b, tol=0.03):
        try:
            return abs(a - b) <= tol * max(a, b)
        except Exception:
            return False

    # Without a pixel size the geometry alone must identify the sensor: exact size (up to the
    # rounding of binned sizes). A 3 % tolerance would turn common video/ROI sizes into cameras,
    # e.g. 640 x 480 into the SBIG ST-i (648 x 486).
    def same_size(a, b, slack):
        return close(a, b, 0.03) if px_candidates else abs(a - b) <= slack

    matches = []
    for item in catalog:
        # Check pixel size if available
        if px_candidates and item['px_um'] > 0 and not any(close(px, item['px_um'], 0.15) for px in px_candidates):
            continue
        
        # Check dimensions
        targets = [(item['w'], item['h'])]
        if 'w_alt' in item and 'h_alt' in item:
            targets.append((item['w_alt'], item['h_alt']))
        
        for (tw, th) in targets:
            if (same_size(w, tw, bw) and same_size(h, th, bh)) or (same_size(w, th, bw) and same_size(h, tw, bh)):
                matches.append(item['name'])
                break  # Only add each instrument once

    if color is not None and len(matches) > 1:
        color_of = {item['name']: item.get('color') for item in catalog}
        same_type = [name for name in matches if color_of.get(name) == color]
        if same_type:
            matches = same_type

    return matches


def detect_instrument(naxis1, naxis2, pixel_um, binx, biny):
    """
    Infer instrument/camera name from geometry and pixel size.
    Accepts binned image sizes; will scale back to unbinned using binning factors.
    
    Returns the first matching instrument, or None if no match.
    For backward compatibility - use detect_instruments() to get all matches.
    """
    matches = detect_instruments(naxis1, naxis2, pixel_um, binx, biny)
    return matches[0] if matches else None


def disambiguate_instrument(possible_instruments, header_instrument, strict=False):
    """
    Disambiguate between multiple possible instruments based on header instrument name.
    
    Args:
        possible_instruments: List of possible instrument names
        header_instrument: Instrument name from FITS header (may be generic or variant)
        strict: Return None instead of the first possible instrument if the name decides nothing
    
    Returns:
        Best matching instrument name, or None if no disambiguation possible
    """
    if not possible_instruments:
        return None
    
    if len(possible_instruments) == 1:
        return possible_instruments[0]
    
    if not header_instrument:
        return None
    
    header_lower = header_instrument.strip().lower()
    
    # Mapping of header patterns to instrument families
    # QHY patterns
    qhy_patterns = [
        (r'qhy\s*600', ['QHY 600M']),
        (r'qhy\s*268', ['QHY 268M']),
        (r'qhy\s*5iii\s*485', ['QHY 5III485C']),
        (r'qhy\s*5iii\s*462', ['QHY 5III462C']),
        (r'qhyccd-cameras-capture', ['QHY 600M', 'QHY 268M']),  # Generic QHY
        (r'qhy', ['QHY 600M', 'QHY 268M', 'QHY 5III485C', 'QHY 5III462C']),  # Generic QHY
    ]
    
    # ZWO patterns
    zwo_patterns = [
        (r'asi\s*2600', ['ZWO ASI2600MC Pro']),
        (r'asi\s*294', ['ZWO ASI294MM Pro']),
        (r'asi\s*174', ['ZWO ASI174MM']),
        (r'asi\s*220', ['ZWO ASI220MM']),
        (r'asi\s*678', ['ZWO ASI678MM']),
        (r'asi\s*533', ['ZWO ASI533MC Pro']),
        (r'asi\s*camera\s*\(1\)', ['ZWO ASI2600MC Pro', 'ZWO ASI294MM Pro', 'ZWO ASI174MM', 'ZWO ASI220MM', 'ZWO ASI678MM', 'ZWO ASI533MC Pro']),  # Generic ZWO
        (r'zwo', ['ZWO ASI2600MC Pro', 'ZWO ASI294MM Pro', 'ZWO ASI174MM', 'ZWO ASI220MM', 'ZWO ASI678MM', 'ZWO ASI533MC Pro']),
    ]
    
    # SBIG patterns
    sbig_patterns = [
        (r'st-?i\b', ['SBIG ST-i']),
        (r'st-?7\b', ['SBIG ST-7']),
        (r'st-?8\b', ['SBIG ST-8']),
        (r'stf-?8300', ['SBIG STF-8300']),
        (r'sbig', ['SBIG ST-i', 'SBIG ST-7', 'SBIG ST-8', 'SBIG STF-8300']),
    ]
    
    # Skyris patterns
    skyris_patterns = [
        (r'skyris\s*445', ['Skyris 445C']),
    ]
    
    import re
    
    # Try to match patterns
    all_patterns = qhy_patterns + zwo_patterns + sbig_patterns + skyris_patterns
    
    for pattern, candidates in all_patterns:
        if re.search(pattern, header_lower):
            # Find intersection of candidates and possible_instruments
            intersection = [inst for inst in candidates if inst in possible_instruments]
            if intersection:
                # If multiple matches, prefer exact name match
                for inst in intersection:
                    if inst.lower() in header_lower or header_lower in inst.lower():
                        return inst
                return intersection[0]  # Return first match
    
    # If no pattern match, try direct name matching
    for inst in possible_instruments:
        inst_lower = inst.lower()
        if inst_lower in header_lower or header_lower in inst_lower:
            return inst
    
    # If still no match, return first possible instrument (a guess; None in strict mode)
    return None if strict else possible_instruments[0]


#   Header values that do not identify a camera
UNKNOWN_INSTRUMENT_NAMES = ('', '-', 'uk', 'unknown')
GENERIC_INSTRUMENT_MARKERS = ('qhyccd-cameras-capture', 'asi camera (1)')


def is_placeholder_instrument(name):
    """Header values that name no camera: empty, 'UK', 'Unknown', 'Unknown Instrument', ..."""
    lower = (name or '').strip().lower()
    return lower in UNKNOWN_INSTRUMENT_NAMES or lower.startswith('unknown')


def resolve_instrument(candidates, header_instrument):
    """
    One camera from the geometry candidates: the only candidate, or the one the header name points
    to (e.g. generic 'QHYCCD-Cameras-Capture' -> QHY). None if ambiguous: no guessing.
    """
    if len(candidates) == 1:
        return candidates[0]
    if candidates and not is_placeholder_instrument(header_instrument):
        return disambiguate_instrument(candidates, header_instrument, strict=True)
    return None


def canonical_instrument(name, naxis1=-1, naxis2=-1, pixel_size=-1, binning_x=1, binning_y=1, color=None):
    """
    Canonical camera name for a raw header/EXIF instrument value: alias-normalized name; missing or
    generic names (e.g. 'QHYCCD-Cameras-Capture') are resolved from the image geometry if possible,
    using the sensor type (color: True/False/None) to tell apart cameras with the same geometry.
    """
    raw = (name or '').strip()
    lower = raw.lower()
    generic = any(marker in lower for marker in GENERIC_INSTRUMENT_MARKERS)
    if is_placeholder_instrument(raw) or generic:
        candidates = detect_instruments(naxis1, naxis2, pixel_size, binning_x, binning_y, color)
        resolved = resolve_instrument(candidates, raw)
        if resolved:
            return normalize_instrument(resolved)
        if not generic:
            return 'Unknown'
    return normalize_instrument(raw)


def analyze_fits(datafile, save=True):
    """
        Extract HEADER information from the FITS files

        Parameters
        ----------
        datafile        : `obs_run.models.DataFile` object
            DataFile instance

        save            : `boolean`, optional
            Save the changes (only when a value differs from the database, so unchanged
            files get no history entry). False: only update the instance (dry runs).

        Returns
        -------
        dict
            {field: (stored value, new value)} for every field that changes
    """
    #   Get Header
    header = datafile.get_fits_header()

    #   Extract info from Header
    header_data = extract_fits_header_info(header)

    #   Set basic values (check override flags for protected fields)
    datafile.hjd = header_data.get('hjd', 2400000.)
    datafile.obs_date = header_data.get('obs_date', '2000-00-00')
    datafile.exptime = header_data.get('exptime', 0.)
    datafile.ra = header_data.get('ra', -1)
    datafile.dec = header_data.get('dec', -1)
    datafile.naxis1 = header_data.get('naxis1', 0.)
    datafile.naxis2 = header_data.get('naxis2', 0.)
    
    # Check override flags before setting protected fields
    if should_allow_auto_update(datafile, 'instrument'):
        datafile.instrument = header_data.get('instrument', 'Unknown')
    if should_allow_auto_update(datafile, 'telescope'):
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

    #   Calculate field of view if pixel_size and focal_length are available
    # Initialize FOV to -1 if not already set
    if datafile.fov_x == -1:
        datafile.fov_x = -1
    if datafile.fov_y == -1:
        datafile.fov_y = -1
    
    # Check if we have the required values for FOV calculation
    pixel_size = datafile.pixel_size
    focal_length = datafile.focal_length
    pixel_size_valid = pixel_size is not None and pixel_size > 0
    focal_length_valid = focal_length is not None and focal_length > 0
    naxis_valid = datafile.naxis1 > 0 and datafile.naxis2 > 0
    
    if pixel_size_valid and focal_length_valid and naxis_valid:
        try:
            assert pixel_size is not None and focal_length is not None
            pixel_size_mm = float(pixel_size) / 1000.0
            focal_length_mm = float(focal_length)
            d = float(datafile.naxis1) * pixel_size_mm
            h = float(datafile.naxis2) * pixel_size_mm

            #   Calculate field of view
            double_focal_len = 2.0 * focal_length_mm
            if double_focal_len > 0:
                fov_x = 2.0 * np.arctan(d / double_focal_len)
                fov_y = 2.0 * np.arctan(h / double_focal_len)

                #   Convert to degree
                two_pi = 2.0 * np.pi
                fov_x_deg = fov_x * 360.0 / two_pi
                fov_y_deg = fov_y * 360.0 / two_pi
                
                # Validate FOV values (reasonable range: 0.001 to 180 degrees)
                if 0.001 <= fov_x_deg <= 180.0 and 0.001 <= fov_y_deg <= 180.0:
                    datafile.fov_x = fov_x_deg
                    datafile.fov_y = fov_y_deg
                    logger.debug(
                        f'FOV calculated for DataFile {datafile.pk}: '
                        f'fov_x={fov_x_deg:.6f}°, fov_y={fov_y_deg:.6f}°'
                    )
                else:
                    # Invalid FOV values, set to -1
                    logger.warning(
                        f'Invalid FOV calculated for DataFile {datafile.pk}: '
                        f'fov_x={fov_x_deg:.6f}°, fov_y={fov_y_deg:.6f}° '
                        f'(pixel_size={datafile.pixel_size}µm, focal_length={datafile.focal_length}mm, '
                        f'naxis1={datafile.naxis1}, naxis2={datafile.naxis2})'
                    )
                    datafile.fov_x = -1
                    datafile.fov_y = -1
            else:
                logger.warning(
                    f'Invalid focal_length for FOV calculation (DataFile {datafile.pk}): '
                    f'focal_length={datafile.focal_length}mm'
                )
                datafile.fov_x = -1
                datafile.fov_y = -1
        except Exception as e:
            logger.warning(
                f'Error calculating FOV for DataFile {datafile.pk}: {e} '
                f'(pixel_size={datafile.pixel_size}, focal_length={datafile.focal_length}, '
                f'naxis1={datafile.naxis1}, naxis2={datafile.naxis2})'
            )
            datafile.fov_x = -1
            datafile.fov_y = -1
    else:
        # Missing required values for FOV calculation
        if not pixel_size_valid:
            logger.debug(
                f'Cannot calculate FOV for DataFile {datafile.pk}: '
                f'invalid pixel_size={datafile.pixel_size}'
            )
        if not focal_length_valid:
            logger.debug(
                f'Cannot calculate FOV for DataFile {datafile.pk}: '
                f'invalid focal_length={datafile.focal_length}'
            )
        if not naxis_valid:
            logger.debug(
                f'Cannot calculate FOV for DataFile {datafile.pk}: '
                f'invalid naxis (naxis1={datafile.naxis1}, naxis2={datafile.naxis2})'
            )
        # Ensure FOV is set to -1 if values are missing
        datafile.fov_x = -1
        datafile.fov_y = -1

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

    #   Sanitize image type (check override flag)
    if should_allow_auto_update(datafile, 'exposure_type'):
        img_type = header_data.get('imagetyp', 'UK')
        for key, value in img_types.items():
            if key == img_type:
                datafile.exposure_type = value
                break
        else:
            datafile.exposure_type = 'UK'

    #   Set object name (header_target_name always mirrors the header; main_target only
    #   unless it was set manually)
    if datafile.exposure_type in ['UK', 'LI']:
        datafile.header_target_name = header_data.get('objectname', '-')
    else:
        datafile.header_target_name = '-'
    #   Files already associated with an object show the object as target (set by the object
    #   evaluation); the header name is only the initial target of unassigned files
    linked = datafile.pk is not None and datafile.object_set.exists()
    if should_allow_auto_update(datafile, 'main_target') and not linked:
        datafile.main_target = datafile.header_target_name

    # Infer instrument from header/geometry if header instrument is generic or missing
    try:
        header_instr = header_data.get('instrument', '') or ''
    except Exception:
        header_instr = ''

    datafile.color_sensor = header_data.get('color_sensor')
    candidates = detect_instruments(
        header_data.get('naxis1', -1),
        header_data.get('naxis2', -1),
        header_data.get('pixel_size', -1),
        header_data.get('binning_x', 1),
        header_data.get('binning_y', 1),
        datafile.color_sensor,
    )
    # Cameras sharing a sensor (e.g. QHY 268M / ZWO ASI2600MC Pro) are told apart by the header name;
    # if nothing decides, no camera is inferred
    inferred = resolve_instrument(candidates, header_instr)

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
    if assign_inferred and should_allow_auto_update(datafile, 'instrument'):
        datafile.instrument = inferred

    #   Derived field (save() keeps it in sync); set here so dry runs report it too
    datafile.instrument_normalized = canonical_instrument(
        datafile.instrument, datafile.naxis1, datafile.naxis2, datafile.pixel_size,
        datafile.binning_x, datafile.binning_y, datafile.color_sensor,
    )

    changes = changed_fields(datafile)
    if save and (changes or datafile.pk is None):
        from ostdata.history_reason import REASON_TASK_ANALYZE_HEADER, save_with_reason
        save_with_reason(datafile, REASON_TASK_ANALYZE_HEADER)
    return changes


def changed_fields(instance):
    """
    {field: (stored value, new value)} for concrete fields whose in-memory value differs from the
    database row (all fields for unsaved instances). New values are cleaned with the field's
    to_python(), so e.g. a header string '1.20' and a stored 1.2 count as equal.
    """
    fields = [f for f in instance._meta.concrete_fields if not f.primary_key]
    stored = None
    if instance.pk is not None:
        stored = type(instance).objects.filter(pk=instance.pk).values(*[f.attname for f in fields]).first()
    changes = {}
    for field in fields:
        new = getattr(instance, field.attname)
        try:
            new = field.to_python(new)
        except Exception:
            pass
        old = stored.get(field.attname) if stored is not None else None
        if stored is None or not _same_value(old, new):
            changes[field.name] = (old, new)
    return changes


def _same_value(old, new):
    if isinstance(old, float) and isinstance(new, float) and math.isnan(old) and math.isnan(new):
        return True
    return old == new
