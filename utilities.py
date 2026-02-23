import os
import re
from pathlib import Path

import numpy as np

from astroquery.simbad import Simbad
from astropy.coordinates.angles import Angle
from astropy.coordinates import SkyCoord, EarthLocation, get_body
import astropy.units as u
from astropy.io import fits
from astropy.time import Time
from astropy.visualization import simple_norm

from scipy import ndimage, signal

import matplotlib.pyplot as plt
import hashlib
import logging

import django
from django.db.models import F, ExpressionWrapper, DecimalField, FloatField, Case, When, Value, Q, CharField

os.environ["DJANGO_SETTINGS_MODULE"] = "ostdata.settings"
django.setup()

from objects.models import Object
from obs_run.models import ObservationRun, DataFile
from obs_run.utils import should_allow_auto_update, object_has_any_override
logger = logging.getLogger(__name__)

import time
import warnings

# Simple in-process SIMBAD safeguards: rate limit and negative cache
_SIMBAD_NEGATIVE_CACHE = set()
_LAST_SIMBAD_TS = 0.0
_SIMBAD_MIN_INTERVAL = float(os.environ.get('SIMBAD_MIN_INTERVAL', '0.3'))

def _simbad_rate_limit():
    global _LAST_SIMBAD_TS
    now = time.time()
    wait = _SIMBAD_MIN_INTERVAL - (now - _LAST_SIMBAD_TS)
    if wait > 0:
        time.sleep(wait)
    _LAST_SIMBAD_TS = time.time()

def _in_neg_cache(name: str) -> bool:
    return bool(name) and (str(name).strip().lower() in _SIMBAD_NEGATIVE_CACHE)

def _add_neg_cache(name: str):
    if name:
        _SIMBAD_NEGATIVE_CACHE.add(str(name).strip().lower())

def _try_add_fields(simbad: Simbad, fields: tuple[str, ...]) -> bool:
    try:
        _simbad_rate_limit()
        simbad.add_votable_fields(*fields)
        return True
    except Exception as e:
        logger.warning("SIMBAD add_votable_fields failed: %s", e)
        return False

def _query_object_variants(name: str):
    if _in_neg_cache(name):
        return None
    base = " ".join(str(name).strip().split())
    variants = {base}
    m = re.match(r"^(M|NGC|IC|UGC|PGC)\s*0*([0-9]+)$", base, re.IGNORECASE)
    if m:
        variants.add(f"{m.group(1).upper()} {int(m.group(2))}")
        variants.add(f"{m.group(1).upper()}{int(m.group(2))}")
    custom = Simbad()
    try:
        custom.ROW_LIMIT = 1
    except Exception:
        pass
    _try_add_fields(custom, ('otype','alltypes','ids'))
    for v in variants:
        try:
            _simbad_rate_limit()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                tbl = custom.query_object(v)
            if tbl is not None and len(tbl) > 0:
                return tbl
        except Exception as e:
            logger.warning("SIMBAD query_object error for %s: %s", v, e)
            break
    _add_neg_cache(name)
    return None

def _query_region_safe(ra_deg: float, dec_deg: float, radius_str: str = '0d5m0s', row_limit: int = 10):
    """
    Query SIMBAD region search safely with rate limiting.
    
    Parameters
    ----------
    ra_deg : float
        Right ascension in degrees
    dec_deg : float
        Declination in degrees
    radius_str : str
        Search radius in SIMBAD format (e.g., '5d0m0s' for 5 arcmin)
    row_limit : int
        Maximum number of rows to return (default: 10)
    
    Returns
    -------
    astropy.table.Table or None
        SIMBAD query results or None on error
    """
    try:
        sim = Simbad()
        try:
            sim.ROW_LIMIT = row_limit
        except Exception:
            pass
        if not _try_add_fields(sim, ('otype','alltypes','ids','V')):
            return None
        _simbad_rate_limit()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return sim.query_region(
                SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame='icrs'),
                radius=radius_str,
            )
    except Exception as e:
        logger.warning("SIMBAD query_region failed: %s", e)
        return None

def compute_file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_object_type_from_simbad_types(types_str: str):
    """
    Detect object type from SIMBAD types string.
    
    Parameters
    ----------
    types_str : str
        SIMBAD types string (e.g., from 'alltypes.otypes' field)
    
    Returns
    -------
    str or None
        Object type code: 'SC' (Star Cluster), 'NE' (Nebula), 'GA' (Galaxy), 'ST' (Star), or None
        Priority order: SC, NE, GA, ST (but caller should apply NE > SC > GA)
    """
    if not types_str:
        return None
    
    types_str = str(types_str)
    
    # Star Cluster patterns
    if 'Cl*' in types_str or 'As*' in types_str or 'OpC' in types_str:
        return 'SC'
    
    # Nebula patterns
    if 'ISM' in types_str or 'PN' in types_str or 'SNR' in types_str or 'HII' in types_str:
        return 'NE'
    
    # Galaxy patterns
    if '|G|' in types_str or 'Sy2' in types_str or 'LIN' in types_str:
        return 'GA'
    
    # Star pattern (lowest priority, checked last)
    if '*' in types_str:
        return 'ST'
    
    return None


def annotate_effective_exposure_type(queryset):
    """
    Annotate a DataFile queryset with annotated_effective_exposure_type field.
    
    This implements the priority logic:
    1. exposure_type_user (if set, not None, not empty string)
    2. exposure_type_ml (if set AND matches exposure_type header value)
    3. 'UK' (Unknown) if exposure_type_ml is set but doesn't match exposure_type
    4. exposure_type (header-based, fallback)
    
    Parameters
    ----------
    queryset : QuerySet
        DataFile queryset to annotate
    
    Returns
    -------
    QuerySet
        Annotated queryset with annotated_effective_exposure_type field
    """
    return queryset.annotate(
        annotated_effective_exposure_type=Case(
            # Priority 1: User-set type
            When(
                Q(exposure_type_user__isnull=False) & ~Q(exposure_type_user=''),
                then='exposure_type_user'
            ),
            # Priority 2: ML type matches header type
            When(
                Q(exposure_type_ml__isnull=False) & 
                ~Q(exposure_type_ml='') & 
                Q(exposure_type_ml=F('exposure_type')),
                then='exposure_type_ml'
            ),
            # Priority 3: ML type doesn't match header type -> Unknown
            When(
                Q(exposure_type_ml__isnull=False) & ~Q(exposure_type_ml=''),
                then=Value('UK')
            ),
            # Priority 4: Header-based type
            default='exposure_type',
            output_field=CharField(max_length=2)
        )
    )


def get_effective_exposure_type_filter(exposure_type_code, field_prefix=''):
    """
    Create a Q filter for filtering by effective exposure type.
    This can be used in Count filters and other aggregations.
    
    Parameters
    ----------
    exposure_type_code : str
        Exposure type code to filter for (e.g., 'LI', 'FL', 'DA')
    field_prefix : str, optional
        Prefix for field names (e.g., 'datafile__' for related fields)
    
    Returns
    -------
    Q
        Django Q object for filtering by effective exposure type
    """
    # This creates a filter that matches the effective_exposure_type logic
    # Priority 1: exposure_type_user matches
    # Priority 2: exposure_type_ml matches AND equals exposure_type
    # Priority 3: exposure_type_ml doesn't match exposure_type -> 'UK' (only if code is 'UK')
    # Priority 4: exposure_type matches
    
    # Build field names with prefix
    user_field = f'{field_prefix}exposure_type_user' if field_prefix else 'exposure_type_user'
    ml_field = f'{field_prefix}exposure_type_ml' if field_prefix else 'exposure_type_ml'
    type_field = f'{field_prefix}exposure_type' if field_prefix else 'exposure_type'
    
    if exposure_type_code == 'UK':
        # For Unknown: exposure_type_ml is set but doesn't match exposure_type
        return Q(
            Q(**{f'{ml_field}__isnull': False}) & 
            ~Q(**{ml_field: ''}) & 
            ~Q(**{ml_field: F(type_field)})
        )
    else:
        # For other types: check all priority levels
        return (
            # Priority 1: exposure_type_user matches
            Q(**{user_field: exposure_type_code}) & 
            Q(**{f'{user_field}__isnull': False}) & 
            ~Q(**{user_field: ''})
        ) | (
            # Priority 2: exposure_type_ml matches AND equals exposure_type
            Q(**{ml_field: exposure_type_code}) & 
            Q(**{f'{ml_field}__isnull': False}) & 
            ~Q(**{ml_field: ''}) & 
            Q(**{ml_field: F(type_field)})
        ) | (
            # Priority 4: exposure_type matches AND (no user type OR no ML type OR ML matches)
            Q(**{type_field: exposure_type_code}) & 
            (
                Q(**{f'{user_field}__isnull': True}) | Q(**{user_field: ''})
            ) & 
            (
                Q(**{f'{ml_field}__isnull': True}) | 
                Q(**{ml_field: ''}) | 
                Q(**{ml_field: F(type_field)})
            )
        )


def get_object_fov_radius(obj, fallback_arcmin=10.0, min_arcmin=1.0, max_arcmin=60.0):
    """
    Calculate FOV radius for an object from associated DataFiles.
    
    Parameters
    ----------
    obj : Object
        Object instance
    fallback_arcmin : float
        Fallback radius in arcmin if no valid FOV found (default: 5.0)
    min_arcmin : float
        Minimum radius in arcmin (default: 1.0)
    max_arcmin : float
        Maximum radius in arcmin (default: 30.0)
    
    Returns
    -------
    str
        Radius string for SIMBAD query (e.g., "5d0m0s" for 5 arcmin)
    """
    # Get associated DataFiles with valid FOV
    # Filter for FOV > 0 (not -1, not 0)
    datafiles = obj.datafiles.filter(
        fov_x__gt=0,
        fov_y__gt=0
    )
    
    # Prefer Light frames (using effective exposure type)
    datafiles = annotate_effective_exposure_type(datafiles)
    light_frames = datafiles.filter(annotated_effective_exposure_type='LI')
    
    if light_frames.exists():
        datafiles = light_frames
    # Otherwise use any DataFile with valid FOV
    
    if not datafiles.exists():
        # Use fallback
        radius_arcmin = fallback_arcmin
    else:
        # Use first DataFile with valid FOV
        df = datafiles.first()
        # Calculate half-diagonal in degrees
        fov_x_deg = float(df.fov_x)
        fov_y_deg = float(df.fov_y)
        half_diagonal_deg = np.sqrt(fov_x_deg**2 + fov_y_deg**2) / 2.0
        # Convert to arcmin
        radius_arcmin = half_diagonal_deg * 60.0
    
    # Apply caps
    radius_arcmin = max(min_arcmin, min(max_arcmin, radius_arcmin))
    
    # Convert to SIMBAD format: "XdYmZs" where X=degrees, Y=arcmin, Z=arcsec
    degrees = int(radius_arcmin // 60)
    remaining_arcmin = radius_arcmin - (degrees * 60)
    arcmin = int(remaining_arcmin)
    arcsec = int((remaining_arcmin - arcmin) * 60)
    
    return f"{degrees}d{arcmin}m{arcsec}s"


def update_observation_run_photometry_spectroscopy(observation_run):
    """
    Automatically update photometry and spectroscopy flags for an ObservationRun
    based on associated DataFiles.
    
    Only updates if override flags are not set.
    
    Parameters
    ----------
    observation_run : ObservationRun
        ObservationRun instance to update
    """
    if not observation_run:
        return
    
    # Check if override flags are set - if so, skip automatic update
    if not should_allow_auto_update(observation_run, 'photometry') and \
       not should_allow_auto_update(observation_run, 'spectroscopy'):
        return
    
    # Get all Light frames associated with this observation run
    light_files = observation_run.datafile_set.filter(exposure_type='LI')
    
    # Check for spectroscopy: Light files with spectrograph != 'N' (NONE)
    has_spectroscopy = light_files.exclude(spectrograph='N').exists()
    
    # Check for photometry: Light files with spectrograph == 'N' (NONE)
    has_photometry = light_files.filter(spectrograph='N').exists()
    
    # Update fields only if override flags allow it
    update_fields = []
    
    if should_allow_auto_update(observation_run, 'spectroscopy'):
        if observation_run.spectroscopy != has_spectroscopy:
            observation_run.spectroscopy = has_spectroscopy
            update_fields.append('spectroscopy')
    
    if should_allow_auto_update(observation_run, 'photometry'):
        if observation_run.photometry != has_photometry:
            observation_run.photometry = has_photometry
            update_fields.append('photometry')
    
    if update_fields:
        observation_run.save(update_fields=update_fields)


def update_object_photometry_spectroscopy(obj):
    """
    Automatically update photometry and spectroscopy flags for an Object
    based on associated DataFiles.
    
    Only updates if override flags are not set.
    
    Parameters
    ----------
    obj : Object
        Object instance to update
    """
    if not obj:
        return
    
    # Check if override flags are set - if so, skip automatic update
    if not should_allow_auto_update(obj, 'photometry') and \
       not should_allow_auto_update(obj, 'spectroscopy'):
        return
    
    # Get all Light frames associated with this object
    # Use effective exposure type for filtering
    light_files = annotate_effective_exposure_type(
        obj.datafiles.all()
    ).filter(annotated_effective_exposure_type='LI')
    
    # Check for spectroscopy: Light files with spectrograph != 'N' (NONE)
    has_spectroscopy = light_files.exclude(spectrograph='N').exists()
    
    # Check for photometry: Light files with spectrograph == 'N' (NONE)
    has_photometry = light_files.filter(spectrograph='N').exists()
    
    # Update fields only if override flags allow it
    update_fields = []
    
    if should_allow_auto_update(obj, 'spectroscopy'):
        if obj.spectroscopy != has_spectroscopy:
            obj.spectroscopy = has_spectroscopy
            update_fields.append('spectroscopy')
    
    if should_allow_auto_update(obj, 'photometry'):
        if obj.photometry != has_photometry:
            obj.photometry = has_photometry
            update_fields.append('photometry')
    
    if update_fields:
        obj.save(update_fields=update_fields)


def get_observatory_location(data_file):
    """
    Extract observatory location from FITS header or use Django settings defaults.
    
    Parameters
    ----------
    data_file : DataFile
        DataFile instance with FITS header information
    
    Returns
    -------
    EarthLocation or None
        EarthLocation object if valid coordinates found, None otherwise
    """
    from django.conf import settings
    
    latitude = None
    longitude = None
    elevation = 0.0
    
    # Try to extract from FITS header
    try:
        header = data_file.get_fits_header()
        
        # Try FITS standard keys first
        if 'OBS-LAT' in header:
            try:
                lat_val = header['OBS-LAT']
                # Handle various formats (degrees, degrees:minutes:seconds, etc.)
                if isinstance(lat_val, (int, float)):
                    latitude = float(lat_val)
                elif isinstance(lat_val, str):
                    # Try parsing as degrees:minutes:seconds or decimal degrees
                    try:
                        latitude = Angle(lat_val).degree
                    except Exception:
                        latitude = float(lat_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if 'OBS-LONG' in header:
            try:
                lon_val = header['OBS-LONG']
                if isinstance(lon_val, (int, float)):
                    longitude = float(lon_val)
                elif isinstance(lon_val, str):
                    try:
                        longitude = Angle(lon_val).degree
                    except Exception:
                        longitude = float(lon_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if 'OBS-ELEV' in header:
            try:
                elevation = float(header['OBS-ELEV'])
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Try alternative keys if standard keys not found
        if latitude is None and 'SITELAT' in header:
            try:
                lat_val = header['SITELAT']
                if isinstance(lat_val, (int, float)):
                    latitude = float(lat_val)
                elif isinstance(lat_val, str):
                    try:
                        latitude = Angle(lat_val).degree
                    except Exception:
                        latitude = float(lat_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if longitude is None and 'SITELONG' in header:
            try:
                lon_val = header['SITELONG']
                if isinstance(lon_val, (int, float)):
                    longitude = float(lon_val)
                elif isinstance(lon_val, str):
                    try:
                        longitude = Angle(lon_val).degree
                    except Exception:
                        longitude = float(lon_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if elevation == 0.0 and 'SITEELEV' in header:
            try:
                elevation = float(header['SITEELEV'])
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Try another set of alternative keys
        if latitude is None and 'LATITUDE' in header:
            try:
                lat_val = header['LATITUDE']
                if isinstance(lat_val, (int, float)):
                    latitude = float(lat_val)
                elif isinstance(lat_val, str):
                    try:
                        latitude = Angle(lat_val).degree
                    except Exception:
                        latitude = float(lat_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if longitude is None and 'LONGITUD' in header:
            try:
                lon_val = header['LONGITUD']
                if isinstance(lon_val, (int, float)):
                    longitude = float(lon_val)
                elif isinstance(lon_val, str):
                    try:
                        longitude = Angle(lon_val).degree
                    except Exception:
                        longitude = float(lon_val)
            except (ValueError, TypeError, AttributeError):
                pass
        
        if elevation == 0.0 and 'ALTITUDE' in header:
            try:
                elevation = float(header['ALTITUDE'])
            except (ValueError, TypeError, AttributeError):
                pass
    
    except Exception as e:
        logger.debug(f'Error extracting observatory location from FITS header for data_file {data_file.pk}: {e}')
    
    # Fall back to Django settings if header extraction failed
    if latitude is None:
        latitude = getattr(settings, 'OBSERVATORY_LATITUDE', None)
    if longitude is None:
        longitude = getattr(settings, 'OBSERVATORY_LONGITUDE', None)
    if elevation == 0.0:
        elevation = getattr(settings, 'OBSERVATORY_ELEVATION', 0.0)
    
    # Validate coordinates
    if latitude is None or longitude is None:
        return None
    
    if not (-90 <= latitude <= 90):
        logger.warning(f'Invalid latitude value: {latitude} (must be between -90 and 90)')
        return None
    
    if not (-180 <= longitude <= 180):
        logger.warning(f'Invalid longitude value: {longitude} (must be between -180 and 180)')
        return None
    
    try:
        return EarthLocation(lat=latitude * u.deg, lon=longitude * u.deg, height=elevation * u.m)
    except Exception as e:
        logger.warning(f'Error creating EarthLocation: {e}')
        return None


def check_solar_system_objects_in_fov(data_file, observatory_location):
    """
    Check if any Solar System objects (Sun, Moon, planets) are in the field of view.
    
    Parameters
    ----------
    data_file : DataFile
        DataFile instance with observation information
    observatory_location : EarthLocation
        Observatory location for calculating object positions
    
    Returns
    -------
    dict
        Dictionary with:
        - 'found': bool indicating if any Solar System object was found
        - 'objects': list of dicts with 'name', 'separation_deg', 'ra', 'dec' for each object found
        - 'closest': dict with the closest object found (if any)
    """
    if observatory_location is None:
        return {'found': False, 'objects': [], 'closest': None}
    
    # Validate required fields
    if (data_file.ra == -1 or data_file.ra is None or data_file.ra == 0.0 or
        data_file.dec == -1 or data_file.dec is None or data_file.dec == 0.0):
        return {'found': False, 'objects': [], 'closest': None}
    
    if data_file.fov_x <= 0 or data_file.fov_y <= 0:
        return {'found': False, 'objects': [], 'closest': None}
    
    if data_file.hjd <= 0:
        return {'found': False, 'objects': [], 'closest': None}
    
    try:
        # Calculate FOV radius (half-diagonal in degrees)
        fov_x_deg = float(data_file.fov_x)
        fov_y_deg = float(data_file.fov_y)
        fov_radius_deg = np.sqrt(fov_x_deg**2 + fov_y_deg**2) / 2.0
        
        # Get observation time
        obs_time = Time(data_file.hjd, format='jd')
        
        # Field center coordinates
        field_center = SkyCoord(ra=data_file.ra * u.deg, dec=data_file.dec * u.deg, frame='icrs')
        
        # List of Solar System objects to check
        solar_system_bodies = [
            'sun', 'moon', 'mercury', 'venus', 'mars', 
            'jupiter', 'saturn', 'uranus', 'neptune'
        ]
        
        found_objects = []
        
        # Check each Solar System object
        for body_name in solar_system_bodies:
            try:
                # Get body position at observation time
                body_coord = get_body(body_name, obs_time, observatory_location)
                
                # Calculate angular separation from field center
                separation = field_center.separation(body_coord)
                separation_deg = separation.to(u.deg).value
                
                # Check if object is within FOV
                if separation_deg <= fov_radius_deg:
                    found_objects.append({
                        'name': body_name.capitalize(),
                        'separation_deg': separation_deg,
                        'ra': body_coord.ra.deg,
                        'dec': body_coord.dec.deg,
                    })
            except Exception as e:
                # Skip this object if there's an error (e.g., ephemeris unavailable)
                logger.debug(f'Error checking {body_name} for data_file {data_file.pk}: {e}')
                continue
        
        # Find closest object if any were found
        closest = None
        if found_objects:
            closest = min(found_objects, key=lambda x: x['separation_deg'])
        
        return {
            'found': len(found_objects) > 0,
            'objects': found_objects,
            'closest': closest,
        }
    
    except Exception as e:
        logger.warning(f'Error checking Solar System objects in FOV for data_file {data_file.pk}: {e}')
        return {'found': False, 'objects': [], 'closest': None}


def verify_star_classification(obj, data_file=None, enable_extended_search=True, fixed_radius_arcmin=None, bypass_override_flags=False):
    """
    Verify if an object classified as 'ST' (star) should actually be a cluster, nebula, or galaxy.
    Performs an extended SIMBAD region search to find nearby SC/NE/GA objects with NGC/M/ACO identifiers.
    
    Parameters
    ----------
    obj : Object
        Object instance that was classified as 'ST'
    data_file : DataFile, optional
        Associated DataFile (used for FOV calculation if available)
    enable_extended_search : bool
        Whether to perform extended search (default: True)
    fixed_radius_arcmin : float, optional
        If provided, use this radius in arcminutes for the SIMBAD search instead of
        computing from FOV. Takes precedence when no data_file FOV is available.
    bypass_override_flags : bool
        If True, ignore override flags when updating (for user-initiated actions).
    
    Returns
    -------
    dict
        Result dictionary with 'updated' (bool), 'best_match' (dict or None), 'candidates' (list)
    """
    import math
    
    # Only check objects classified as stars
    if obj.object_type != 'ST':
        return {'updated': False, 'best_match': None, 'candidates': []}
    
    # Skip if coordinates are invalid
    if obj.ra == -1 or obj.dec == -1 or obj.ra == 0 or obj.dec == 0:
        return {'updated': False, 'best_match': None, 'candidates': []}
    
    if not enable_extended_search:
        return {'updated': False, 'best_match': None, 'candidates': []}
    
    try:
        # Calculate FOV radius for search
        # If fixed_radius_arcmin provided, use it; else if data_file has FOV use it; else use object's DataFiles
        radius_arcmin = 5.0  # Default fallback
        min_radius = 1.0
        max_radius = 30.0
        
        if fixed_radius_arcmin is not None:
            radius_arcmin = max(min_radius, min(max_radius, float(fixed_radius_arcmin)))
        elif data_file and data_file.fov_x > 0 and data_file.fov_y > 0:
            # Use FOV from the current data file
            fov_x_deg = float(data_file.fov_x)
            fov_y_deg = float(data_file.fov_y)
            half_diagonal_deg = np.sqrt(fov_x_deg**2 + fov_y_deg**2) / 2.0
            radius_arcmin = half_diagonal_deg * 60.0
            radius_arcmin = max(min_radius, min(max_radius, radius_arcmin))
        else:
            # Use FOV from associated DataFiles
            radius_str = get_object_fov_radius(
                obj,
                fallback_arcmin=radius_arcmin,
                min_arcmin=min_radius,
                max_arcmin=max_radius
            )
            # Parse radius string to get arcmin
            import re
            match = re.match(r'(\d+)d(\d+)m(\d+)s', radius_str)
            if match:
                degrees = int(match.group(1))
                arcmin = int(match.group(2))
                arcsec = int(match.group(3))
                radius_arcmin = degrees * 60 + arcmin + arcsec / 60.0
            else:
                radius_arcmin = 5.0
        
        # Convert to SIMBAD format
        degrees = int(radius_arcmin // 60)
        remaining_arcmin = radius_arcmin - (degrees * 60)
        arcmin = int(remaining_arcmin)
        arcsec = int((remaining_arcmin - arcmin) * 60)
        radius_str = f"{degrees}d{arcmin}m{arcsec}s"
        
        # Query SIMBAD with extended radius
        result_table = _query_region_safe(
            obj.ra,
            obj.dec,
            radius_str,
            row_limit=1000  
        )
        
        if result_table is None or len(result_table) == 0:
            return {'updated': False, 'best_match': None, 'candidates': []}
        
        # Priority order: NE > SC > GA
        priority_types = ['NE', 'SC', 'GA']
        priority_order = {t: i for i, t in enumerate(priority_types)}
        
        # Filter results for SC, NE, GA types with NGC/M/ACO identifiers
        candidates = []
        for row in result_table:
            raw_types = row.get('alltypes.otypes', None)
            types_str = '' if raw_types is None else str(raw_types)
            detected_type = detect_object_type_from_simbad_types(types_str)
            
            if detected_type in priority_types:
                # Check for NGC, Messier (M), or ACO identifiers
                main_id = str(row.get('main_id', '')).upper()
                
                # Get all identifiers from IDS field
                ids_field = None
                try:
                    ids_field = row.get('IDS', None)
                except Exception:
                    try:
                        ids_field = row.get('ids', None)
                    except Exception:
                        ids_field = None
                
                all_ids = []
                if ids_field is not None:
                    all_ids = [str(id_str).strip().upper() for id_str in str(ids_field).split('|')]
                if main_id:
                    all_ids.append(main_id)
                
                # Check if any identifier contains NGC, M, or ACO
                has_valid_identifier = False
                identifier_match = None
                for id_str in all_ids:
                    # Check for NGC
                    if id_str.startswith('NGC') or ' NGC ' in id_str:
                        has_valid_identifier = True
                        identifier_match = id_str
                        break
                    # Check for Messier
                    if (id_str.startswith('M ') or (id_str.startswith('M') and len(id_str) > 1 and id_str[1].isdigit())) or \
                       id_str.startswith('MESSIER'):
                        has_valid_identifier = True
                        identifier_match = id_str
                        break
                    # Check for ACO
                    if id_str.startswith('ACO') or ' ACO ' in id_str:
                        has_valid_identifier = True
                        identifier_match = id_str
                        break
                
                if not has_valid_identifier:
                    continue  # Skip objects without NGC/M/ACO identifiers
                
                # Extract magnitude (V-band) if available
                magnitude = None
                try:
                    v_mag = row.get('V', None)
                    if v_mag is not None and str(v_mag) != '--' and str(v_mag) != '':
                        try:
                            magnitude = float(v_mag)
                        except (ValueError, TypeError):
                            magnitude = None
                except Exception:
                    magnitude = None
                
                candidates.append({
                    'row': row,
                    'type': detected_type,
                    'magnitude': magnitude,
                    'name': str(row.get('main_id', 'Unknown')),
                    'identifier': identifier_match,
                })
        
        if not candidates:
            return {'updated': False, 'best_match': None, 'candidates': []}
        
        # Sort by priority (NE > SC > GA) and then by magnitude (brighter = better)
        def sort_key(x):
            priority = priority_order.get(x['type'], 999)
            mag_value = x['magnitude'] if x['magnitude'] is not None else 999.0
            return (priority, mag_value)
        
        candidates.sort(key=sort_key)
        best_match = candidates[0]
        
        # Update object if a better match was found
        update_result = update_object_from_simbad_result(
            obj,
            best_match['row'],
            priority_types=priority_types,
            dry_run=False,
            bypass_override_flags=bypass_override_flags,
        )
        
        return {
            'updated': len(update_result.get('updated_fields', [])) > 0,
            'best_match': best_match,
            'candidates': candidates,
            'update_result': update_result,
        }
        
    except Exception as e:
        logger.warning(f'Error verifying star classification for object {obj.pk}: {e}')
        return {'updated': False, 'best_match': None, 'candidates': []}


def reanalyse_object_from_simbad(obj, fixed_radius_arcmin=10.0, dry_run=False, bypass_override_flags=True):
    """
    Re-analyse an object using SIMBAD coordinates query. Updates name, object_type,
    and identifiers. If object_type is ST, verifies star classification with
    extended search. Propagates name changes to associated DataFiles.
    
    Parameters
    ----------
    obj : Object
        Object instance to re-analyse
    fixed_radius_arcmin : float
        Search radius in arcminutes for SIMBAD region query (default: 10.0)
    dry_run : bool
        If True, don't save changes (default: False)
    bypass_override_flags : bool
        If True, ignore override flags and apply all updates (default: True for
        this user-initiated action).
    
    Returns
    -------
    dict
        Result with 'success', 'error', 'updated_fields', 'new_name', 'object_type',
        'identifiers_created', 'star_verification_updated'
    """
    if obj.ra in (-1, None, 0) or obj.dec in (-1, None, 0):
        return {'success': False, 'error': 'Invalid coordinates for SIMBAD query'}
    
    try:
        radius_str = '0d10m0s'
        if fixed_radius_arcmin > 0:
            deg = int(fixed_radius_arcmin // 60)
            rem = fixed_radius_arcmin - deg * 60
            am = int(rem)
            asec = int((rem - am) * 60)
            radius_str = f"{deg}d{am}m{asec}s"
        
        result_table = _query_region_safe(obj.ra, obj.dec, radius_str, row_limit=500)
        if result_table is None or len(result_table) == 0:
            return {'success': False, 'error': f'No SIMBAD result found for coordinates'}
        
        # Use brightest object if V magnitude available, else first (closest)
        index = 0
        if not np.all(result_table['V'].mask):
            index = int(np.argmin(result_table['V'].data))
        row = result_table[index]
        
        update_result = update_object_from_simbad_result(
            obj,
            row,
            priority_types=['NE', 'SC', 'GA', 'ST'],
            dry_run=dry_run,
            allow_all_types=True,
            bypass_override_flags=bypass_override_flags,
        )
        
        star_verification_updated = False
        if not dry_run and obj.object_type == 'ST':
            verification_result = verify_star_classification(
                obj,
                data_file=None,
                enable_extended_search=True,
                fixed_radius_arcmin=fixed_radius_arcmin,
                bypass_override_flags=bypass_override_flags,
            )
            star_verification_updated = verification_result.get('updated', False)
        
        return {
            'success': True,
            'updated_fields': update_result.get('updated_fields', []),
            'new_name': update_result.get('new_name'),
            'object_type': update_result.get('new_object_type'),
            'identifiers_created': update_result.get('identifiers_created', 0),
            'identifiers_deleted': update_result.get('identifiers_deleted', 0),
            'star_verification_updated': star_verification_updated,
        }
    except Exception as e:
        logger.exception('reanalyse_object_from_simbad failed for object %s: %s', obj.pk, e)
        return {'success': False, 'error': str(e)}


def propagate_object_name_to_datafiles(obj):
    """
    Update main_target on all DataFiles associated with obj to obj.name.
    Respects should_allow_auto_update for each DataFile's main_target.
    """
    if not obj or not obj.name:
        return
    for df in obj.datafiles.all():
        if should_allow_auto_update(df, 'main_target'):
            df.main_target = obj.name
            df.save(update_fields=['main_target'])


def update_object_from_simbad_result(obj, simbad_table_row, priority_types=['NE', 'SC', 'GA'], dry_run=False, allow_all_types=False, bypass_override_flags=False):
    """
    Update object from SIMBAD result, respecting override flags unless bypassed.
    
    Parameters
    ----------
    obj : Object
        Object instance to update
    simbad_table_row : astropy.table.Row
        Single row from SIMBAD query result
    priority_types : list
        List of object types to prioritize (default: ['NE', 'SC', 'GA'])
        If multiple matches found, highest priority in this list wins
    dry_run : bool
        If True, don't save changes (default: False)
    allow_all_types : bool
        If True, accept any detected type including 'ST' (star).
        If False, only types in priority_types are accepted (default: False)
    bypass_override_flags : bool
        If True, ignore override flags and apply all updates (for user-initiated
        actions like explicit re-analyse). Default: False.
    
    Returns
    -------
    dict
        Dictionary with 'updated_fields' (list), 'new_object_type', 'new_name', 'identifiers_created' (int)
    """
    result = {
        'updated_fields': [],
        'new_object_type': None,
        'new_name': None,
        'identifiers_created': 0,
    }
    
    # Extract SIMBAD data
    raw_types = simbad_table_row.get('alltypes.otypes', None)
    types_str = '' if raw_types is None else str(raw_types)
    
    # Detect object type
    detected_type = detect_object_type_from_simbad_types(types_str)
    if detected_type is None:
        # Fallback to star if '*' in types
        if '*' in types_str:
            detected_type = 'ST'
        else:
            return result  # No valid type detected
    
    # Check if detected type is in priority list (or allow all types)
    if not allow_all_types and detected_type not in priority_types:
        return result  # Not a type we're interested in
    
    # Extract coordinates
    simbad_ra = Angle(simbad_table_row['ra'], unit='degree').degree
    simbad_dec = Angle(simbad_table_row['dec'], unit='degree').degree
    
    # Extract name
    main_id = simbad_table_row.get('main_id', None)
    new_name = str(main_id) if main_id else obj.name
    
    # Extract identifiers
    aliases_field = None
    try:
        aliases_field = simbad_table_row['IDS']
    except Exception:
        try:
            aliases_field = simbad_table_row['ids']
        except Exception:
            aliases_field = None
    
    aliases = []
    if aliases_field is not None:
        aliases = str(aliases_field).split('|')
    
    # Create SIMBAD href
    sanitized_name = new_name.replace(" ", "").replace('+', "%2B")
    simbad_href = f"https://simbad.u-strasbg.fr/simbad/sim-id?Ident={sanitized_name}"
    
    # Check override flags and update fields (or bypass if user explicitly requested)
    def can_update(field_name):
        return bypass_override_flags or should_allow_auto_update(obj, field_name)

    update_fields = []

    # Update object_type
    if can_update('object_type'):
        if obj.object_type != detected_type:
            obj.object_type = detected_type
            update_fields.append('object_type')
            result['updated_fields'].append('object_type')
            result['new_object_type'] = detected_type
    
    # Update coordinates
    if can_update('ra'):
        if abs(obj.ra - simbad_ra) > 0.0001:  # Small tolerance for float comparison
            obj.ra = simbad_ra
            update_fields.append('ra')
            result['updated_fields'].append('ra')
    
    if can_update('dec'):
        if abs(obj.dec - simbad_dec) > 0.0001:
            obj.dec = simbad_dec
            update_fields.append('dec')
            result['updated_fields'].append('dec')
    
    # Update name
    if can_update('name'):
        if obj.name != new_name:
            obj.name = new_name
            update_fields.append('name')
            result['updated_fields'].append('name')
            result['new_name'] = new_name
    
    # Update simbad_resolved flag
    if can_update('simbad_resolved'):
        if not obj.simbad_resolved:
            obj.simbad_resolved = True
            update_fields.append('simbad_resolved')
            result['updated_fields'].append('simbad_resolved')
    
    # Save object if there are updates
    if update_fields and not dry_run:
        obj.save(update_fields=update_fields)
        if 'name' in update_fields:
            propagate_object_name_to_datafiles(obj)

    # Replace identifiers (delete old non-header-based, create new)
    if not dry_run:
        # Delete all existing identifiers except header-based ones
        deleted_count = obj.identifier_set.filter(info_from_header=False).delete()[0]
        
        # Create new identifiers from SIMBAD
        identifiers_created = 0
        for alias in aliases:
            if alias and alias.strip():
                obj.identifier_set.create(
                    name=alias.strip(),
                    href=simbad_href,
                    info_from_header=False,
                )
                identifiers_created += 1
        
        result['identifiers_created'] = identifiers_created
        result['identifiers_deleted'] = deleted_count
    else:
        # In dry-run, just count what would be created
        result['identifiers_created'] = len([a for a in aliases if a and a.strip()])
        result['identifiers_deleted'] = obj.identifier_set.count()
    
    return result


def add_new_observation_run(data_path, print_to_terminal=False,
                            add_data_files=False):
    """
    Adds new observation run and all associated objects and datasets
    if requested

    Parameters
    ----------
    data_path           : `pathlib.Path`
        Path to the directory with the observation data

    print_to_terminal   : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    add_data_files      : `boolean`, optional
        If True also data files and objects will be added to the database.
        Default is ``False``.
    """
    #   Regular expression definitions for allowed directory name
    rex1 = re.compile(r"^[0-9]{8}$")
    rex2 = re.compile(r"^[0-9]{4}.[0-9]{2}.[0-9]{2}$")
    #   Also allow names like YYYY-MM-DD_suffix (e.g., 2023-11-01_test)
    rex3 = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}_[^/\\]+$")

    #   Get name of observation run
    basename = data_path.name
    if rex1.match(basename) or rex2.match(basename) or rex3.match(basename):
        #   Create new run
        new_observation_run = ObservationRun(
            name=basename,
            reduction_status='NE',
        )
        new_observation_run.save()
        if print_to_terminal:
            print('Run: ', basename)

        #   Process data files
        if add_data_files:
            for (root, dirs, files) in os.walk(data_path, topdown=True):
                for f in files:
                    file_path = Path(root, f)
                    successful = add_new_data_file(
                        file_path,
                        new_observation_run,
                        print_to_terminal=print_to_terminal
                    )
                    if not successful:
                        continue

            #   Set time of observation run -> mid of observation
            datafiles = new_observation_run.datafile_set.filter(
                hjd__gt=2451545
            )
            start_jd = datafiles.order_by('hjd')
            # print(start_jd)
            if not start_jd:
                new_observation_run.mid_observation_jd = 0.
            else:
                start_jd = start_jd[0].hjd
                end_jd = datafiles.order_by('hjd').reverse()
                if not end_jd:
                    new_observation_run.mid_observation_jd = start_jd
                else:
                    end_jd = end_jd[0].hjd
                    new_observation_run.mid_observation_jd = start_jd + (end_jd - start_jd) / 2.
            new_observation_run.save()
            if print_to_terminal:
                print('----------------------------------------')
                print()


def add_new_data_file(path_to_file, observation_run, print_to_terminal=False):
    """
    Adds new dataset and associated objects

    Parameters
    ----------
    path_to_file                : `pathlib.Path`
        Path to the data file

    observation_run             : `obs_run.models.ObservationRun`
        Observation run to which the data file belongs

    print_to_terminal           : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    Returns
    -------
                                : `boolean`
        Returns True if data files and objects were added successfully.
    """
    if print_to_terminal:
        print('File: ', path_to_file.absolute())

    suffix = path_to_file.suffix
    if suffix in ['.fit', '.fits', '.FIT', '.FITS']:
        file_type = 'FITS'
    elif suffix in ['.CR2', '.cr2']:
        file_type = 'CR2'
    elif suffix in ['.JPG', '.jpg', '.jpeg', '.JPEG']:
        file_type = 'JPG'
    elif suffix in ['.tiff', '.tif', '.TIF', '.TIFF']:
        file_type = 'TIFF'
    elif suffix in ['.ser', '.SER']:
        file_type = 'SER'
    elif suffix in ['.avi', '.AVI']:
        file_type = 'AVI'
    elif suffix in ['.mov', '.MOV']:
        file_type = 'MOV'
    else:
        return False

    abs_path = path_to_file.absolute()
    try:
        file_size = abs_path.stat().st_size
    except Exception:
        file_size = 0
    try:
        content_hash = compute_file_hash(abs_path)
    except Exception:
        content_hash = ''

    # Duplicate detection: skip if same absolute path already tracked
    existing_by_path = DataFile.objects.filter(datafile=str(abs_path)).first()
    if existing_by_path is not None:
        try:
            logger.warning("Duplicate path in run %s: skipping %s (already tracked as #%s)",
                           getattr(observation_run, 'name', '?'), str(abs_path), existing_by_path.pk)
        except Exception:
            pass
        return False

    # Duplicate detection within the same run by size+hash (only when hash present)
    if content_hash:
        dup_qs = DataFile.objects.filter(
            observation_run=observation_run,
            content_hash=content_hash,
            file_size=file_size,
        )
        if dup_qs.exists():
            try:
                logger.warning("Duplicate content in run %s: skipping %s (matches #%s)",
                               getattr(observation_run, 'name', '?'), str(abs_path), dup_qs.first().pk)
            except Exception:
                pass
            return False

    data_file = DataFile(
        observation_run=observation_run,
        datafile=abs_path,
        file_type=file_type,
        file_size=file_size,
        content_hash=content_hash,
    )
    data_file.save()

    #   Populate header info (exposure_type, ra, dec, etc.) before ML and evaluation
    try:
        data_file.set_info()
        data_file.save()
    except Exception as e:
        logger.warning(f'Error in set_info() for data_file {data_file.pk}: {e}')

    #   ML-based exposure type classification (if enabled) - run before evaluate_data_file
    #   so effective_exposure_type can consider ML result for object association
    try:
        from django.conf import settings
        if getattr(settings, 'ML_EXPOSURE_TYPE_ENABLED', False):
            from obs_run.ml_classification import ExposureTypeClassifier
            classifier = ExposureTypeClassifier()
            if classifier.is_supported_format(file_type, path_to_file):
                result = classifier.classify_datafile(data_file)
                if result.get('error') is None:
                    data_file.exposure_type_ml = result.get('exposure_type_ml')
                    data_file.exposure_type_ml_confidence = result.get('exposure_type_ml_confidence')
                    data_file.exposure_type_ml_abstained = result.get('exposure_type_ml_abstained', False)
                    # Set spectrograph if ML detected one and no override is set
                    spectrograph_ml = result.get('spectrograph_ml')
                    if spectrograph_ml and not data_file.spectrograph_override:
                        data_file.spectrograph = spectrograph_ml
                        data_file.save(update_fields=[
                            'exposure_type_ml',
                            'exposure_type_ml_confidence',
                            'exposure_type_ml_abstained',
                            'spectrograph',
                        ])
                    else:
                        data_file.save(update_fields=[
                            'exposure_type_ml',
                            'exposure_type_ml_confidence',
                            'exposure_type_ml_abstained',
                        ])
                    
                    if print_to_terminal:
                        print(f'ML Classification: {result.get("exposure_type_ml")} '
                              f'(confidence: {result.get("exposure_type_ml_confidence", 0.0):.3f})')
                elif print_to_terminal:
                    logger.warning(f'ML classification error for {path_to_file}: {result.get("error")}')
    except Exception as e:
        # Don't fail file addition if ML classification fails
        logger.warning(f'ML classification failed for {path_to_file}: {e}', exc_info=True)

    #   Evaluate data file (object association) - runs after ML so effective_exposure_type
    #   can consider exposure_type_ml when deciding if this is a Light frame
    evaluate_data_file(
        data_file,
        observation_run,
        print_to_terminal=print_to_terminal,
    )

    #   Update photometry/spectroscopy flags after object association
    try:
        if data_file.observation_run:
            update_observation_run_photometry_spectroscopy(data_file.observation_run)
        for obj in data_file.object_set.all():
            update_object_photometry_spectroscopy(obj)
    except Exception as e:
        logger.warning(f'Error updating photometry/spectroscopy flags: {e}')

    return True


def evaluate_data_file(data_file, observation_run, print_to_terminal=False, skip_if_object_has_overrides=True, dry_run=False, use_wcs_coords_for_lookup=False):
    """
    Evaluate data file and add associated objects

    Parameters
    ----------
    data_file           : `obs_run.models.DataFile`
        DataFile object

    observation_run             : `obs_run.models.ObservationRun`
        Observation run to which the data file belongs

    print_to_terminal           : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.
    
    skip_if_object_has_overrides : `boolean`, optional
        If True, skip re-assignment if existing objects have override flags set.
        Default is ``True``.
    
    dry_run                     : `boolean`, optional
        If True, simulate evaluation without making database changes.
        Default is ``False``.
    
    use_wcs_coords_for_lookup   : `boolean`, optional
        If True and data_file is plate-solved with valid wcs_ra/wcs_dec, use those
        coordinates for object lookup/SIMBAD queries instead of header ra/dec.
        Use for re-evaluation of plate-solved files (manual or automatic).
        Default is ``False``.
        
    Returns
    -------
    dict
        Dictionary with status information:
        - 'status': 'assigned', 'skipped', 'new_object_created', 'no_match'
        - 'object': assigned object (if any)
        - 'skipped_reason': reason for skipping (if skipped)
        - 'new_object': newly created object (if created)
    """
    # Check if data_file is already associated with objects that have override flags
    existing_objects = list(data_file.object_set.all())
    if existing_objects and skip_if_object_has_overrides:
        for existing_obj in existing_objects:
            if object_has_any_override(existing_obj):
                return {
                    'status': 'skipped',
                    'skipped_reason': 'object_has_overrides',
                    'object': existing_obj
                }
    
    #   Set data file information from file header data
    if not dry_run:
        try:
            data_file.set_info()
            data_file.save()
        except Exception as e:
            logger.warning(f'Error in set_info() for data_file {data_file.pk}: {e}')
            # Continue anyway - some fields might already be set
        # Update file metadata (size/hash) to reflect any external changes
        try:
            p = Path(str(data_file.datafile))
            data_file.file_size = p.stat().st_size if p.exists() else 0
            try:
                data_file.content_hash = compute_file_hash(p) if p.exists() else ''
            except Exception:
                # Keep previous hash if reading fails
                pass
            data_file.save(update_fields=['file_size', 'content_hash'])
        except Exception:
            pass

    # Choose coordinates for object lookup: WCS (plate-solved) or header
    if use_wcs_coords_for_lookup and data_file.plate_solved and data_file.wcs_ra is not None and data_file.wcs_dec is not None:
        lookup_ra = data_file.wcs_ra
        lookup_dec = data_file.wcs_dec
    else:
        lookup_ra = data_file.ra
        lookup_dec = data_file.dec

    target = (data_file.main_target or '').strip()
    expo_type = data_file.effective_exposure_type  # Use effective exposure type
    target_lower = target.lower()

    solar_system = [
        'Sun', 'sun', 'Mercury', 'mercury', 'Venus', 'venus', 'Moon', 'moon',
        'Mond', 'mond', 'Mars', 'mars', 'Jupiter', 'jupiter', 'Saturn',
        'saturn', 'Uranus', 'uranus', 'Neptun', 'neptun', 'Pluto', 'pluto',
    ]

    #   Look for associated objects
    if (
            target_lower != '' and
            target_lower != 'unknown' and
            expo_type == 'LI' and
            'flat' not in target_lower and
            'dark' not in target_lower and
            lookup_ra != -1 and
            lookup_ra is not None and
            lookup_ra != 0. and
            lookup_dec != -1 and
            lookup_dec is not None and
            lookup_dec != 0.
    ):
        try:
            #   Tolerance in degree
            # t = 0.1
            t = 0.5

            if target in solar_system:
                objs = Object.objects.filter(name__icontains=target)
            else:
                # First, filter by a bounding box to reduce candidates
                bbox = Object.objects \
                    .filter(ra__range=(lookup_ra - t, lookup_ra + t)) \
                    .filter(dec__range=(lookup_dec - t, lookup_dec + t))
                # Annotate squared angular distance (no sqrt needed for ordering)
                dist_sq = ExpressionWrapper(
                    (F('ra') - lookup_ra) * (F('ra') - lookup_ra) +
                    (F('dec') - lookup_dec) * (F('dec') - lookup_dec),
                    output_field=FloatField()
                )
                objs = bbox.annotate(distance_sq=dist_sq).order_by('distance_sq')

            if objs.exists():
                if print_to_terminal:
                    print('Object already known (target: {})'.format(target))
                obj = objs.first()
                # Extra safety: if not in bbox case, also try exact/iexact name match
                # Update object fields only if override flags allow it
                if obj:
                    if should_allow_auto_update(obj, 'is_main'):
                        obj.is_main = True
                    obj.save()
                    # Update first_hjd only if override flag allows
                    if should_allow_auto_update(obj, 'first_hjd'):
                        if (obj.first_hjd == 0. or
                                obj.first_hjd == -1. or
                                data_file.hjd < obj.first_hjd):
                            obj.first_hjd = data_file.hjd
                            obj.save(update_fields=['first_hjd'])
            else:
                obj = None
                # # Fallback 1: strict name match
                # by_name = Object.objects.filter(name__iexact=target)
                # if by_name.exists():
                #     obj = by_name.first()
                # else:
                #     by_name_ic = Object.objects.filter(name__icontains=target)
                #     if by_name_ic.exists():
                #         obj = by_name_ic.first()
                #     else:
                #         obj = None

            if obj is not None:
                if not dry_run:
                    # Remove old associations if this is a different object
                    old_objects = list(data_file.object_set.exclude(pk=obj.pk).all())
                    for old_obj in old_objects:
                        old_obj.datafiles.remove(data_file)
                    
                    obj.datafiles.add(data_file)
                    obj.observation_run.add(observation_run)
                    
                    # Update object fields only if override flags allow it
                    update_fields = []
                    
                    if should_allow_auto_update(obj, 'is_main'):
                        obj.is_main = True
                        update_fields.append('is_main')

                    #   Update JD the object was first observed
                    if should_allow_auto_update(obj, 'first_hjd'):
                        if (obj.first_hjd == 0. or
                                obj.first_hjd > data_file.hjd):
                            obj.first_hjd = data_file.hjd
                            update_fields.append('first_hjd')

                    if update_fields:
                        obj.save(update_fields=update_fields)
                    else:
                        obj.save()

                    #   Set datafile target name to identified object name
                    #   This should always be updated when an object is identified,
                    #   regardless of whether it was resolved via Simbad or not
                    if should_allow_auto_update(data_file, 'main_target'):
                        data_file.main_target = obj.name
                        data_file.save()

                    #   Add header name as an alias
                    identifiers = obj.identifier_set.filter(
                        name__exact=target
                    )
                    if len(identifiers) == 0:
                        obj.identifier_set.create(
                            name=target,
                            info_from_header=True,
                        )
                    
                    #   Automatically update photometry/spectroscopy flags for object and observation run
                    if not dry_run:
                        update_object_photometry_spectroscopy(obj)
                        update_observation_run_photometry_spectroscopy(observation_run)
                
                return {'status': 'assigned', 'object': obj}

            #   Handling of Solar system objects
            elif obj is None and target in solar_system:
                if print_to_terminal:
                    print('New object (target: {})'.format(target))
                #     Make a new object
                obj = Object(
                    name=target,
                    ra=lookup_ra,
                    dec=lookup_dec,
                    object_type='SO',
                    simbad_resolved=False,
                    first_hjd=data_file.hjd,
                    is_main=True,
                )
                if not dry_run:
                    obj.save()
                    obj.observation_run.add(observation_run)
                    obj.datafiles.add(data_file)
                    obj.save()
                    #   Automatically update photometry/spectroscopy flags for object and observation run
                    update_object_photometry_spectroscopy(obj)
                    update_observation_run_photometry_spectroscopy(observation_run)
                return {'status': 'new_object_created', 'new_object': obj}

            else:
                if print_to_terminal:
                    print('New object (target: {})'.format(target))
                
                #   Check for Solar System objects in field of view before SIMBAD queries
                #   This check should run before verify_star_classification()
                solar_system_detected = False
                try:
                    # Only check if we have valid FOV and observation time
                    if (data_file.fov_x > 0 and data_file.fov_y > 0 and 
                        data_file.hjd > 0 and expo_type == 'LI'):
                        observatory_location = get_observatory_location(data_file)
                        if observatory_location is not None:
                            sso_result = check_solar_system_objects_in_fov(data_file, observatory_location)
                            if sso_result['found'] and sso_result['closest'] is not None:
                                solar_system_detected = True
                                closest_obj = sso_result['closest']
                                object_name = closest_obj['name']
                                object_ra = closest_obj['ra']
                                object_dec = closest_obj['dec']
                                object_type = 'SO'
                                object_simbad_resolved = False
                                
                                if print_to_terminal:
                                    logger.info(
                                        f'Solar System object detected in FOV: {object_name} '
                                        f'(separation: {closest_obj["separation_deg"]:.3f} deg)'
                                    )
                except Exception as e:
                    # Don't fail object creation if Solar System check fails
                    logger.warning(f'Error checking Solar System objects in FOV for data_file {data_file.pk}: {e}')
                
                #   Set Defaults (will be overridden if Solar System object was detected)
                if not solar_system_detected:
                    object_ra = lookup_ra
                    object_dec = lookup_dec
                    object_type = 'UK'
                    object_simbad_resolved = False
                    object_name = target

                    #   Query Simbad for object name (safe, with variants and rate-limit)
                    simbad_tbl = _query_object_variants(target)

                    #   Get Simbad coordinates
                    if simbad_tbl is not None and len(simbad_tbl) > 0:
                        simbad_ra = Angle(
                            simbad_tbl[0]['ra'],
                            unit='degree',
                        ).degree
                        simbad_dec = Angle(
                            simbad_tbl[0]['dec'],
                            unit='degree',
                        ).degree

                        # #   Tolerance in degree
                        # tol = 0.5
                        # tol = 1.

                        if (simbad_ra + t > lookup_ra > simbad_ra - t and
                                simbad_dec + t > lookup_dec > simbad_dec - t):
                            object_ra = simbad_ra
                            object_dec = simbad_dec
                            object_simbad_resolved = True
                            object_data_table = simbad_tbl[0]

                        if print_to_terminal:
                            print('Object resolved based on name:')
                            print(object_simbad_resolved)

                    #   Search Simbad based on coordinates
                    if not object_simbad_resolved:
                        result_table = _query_region_safe(lookup_ra, lookup_dec, '0d5m0s', row_limit=10)

                        if (result_table is not None and
                                len(result_table) > 0):

                            #   Get the brightest object if magnitudes
                            #   are available otherwise use the object
                            #   with the smallest distance to the
                            #   coordinates
                            if np.all(result_table['V'].mask):
                                index = 0
                            else:
                                index = np.argmin(
                                    result_table['V'].data
                                )
                            simbad_ra = Angle(
                                result_table[index]['ra'],
                                unit='degree',
                            ).degree
                            simbad_dec = Angle(
                                result_table[index]['dec'],
                                unit='degree',
                            ).degree
                            object_ra = simbad_ra
                            object_dec = simbad_dec
                            object_simbad_resolved = True
                            object_data_table = result_table[index]

                            if print_to_terminal:
                                print('Object resolved based on coordinates:')
                                print(object_simbad_resolved)

                    #   Set object type based on Simbad
                    if object_simbad_resolved:
                        # print('object_data_table:')
                        # print(object_data_table.pprint(max_lines=-1, max_width=-1))
                        # print(object_data_table)

                        raw_types = object_data_table['alltypes.otypes']
                        types_str = '' if raw_types is None else str(raw_types)
                        # print('types_str:')
                        # print(types_str)

                        #   Decode information in object string to get a rough object estimate
                        object_type = detect_object_type_from_simbad_types(types_str)
                        if object_type is None:
                            # Fallback: if no specific type detected, check for star
                            if '*' in types_str:
                                object_type = 'ST'
                            else:
                                object_type = 'UK'  # Unknown - never leave object_type as None (DB constraint)

                        #   Set default name
                        main_id = object_data_table['main_id']
                        if main_id:
                            object_name = str(main_id)

                #     Make a new object (new objects don't have override flags set)
                # Ensure object_type is never None (DB NOT NULL constraint)
                if object_type is None:
                    object_type = 'UK'
                obj = Object(
                    name=object_name,
                    ra=object_ra,
                    dec=object_dec,
                    object_type=object_type,
                    simbad_resolved=object_simbad_resolved,
                    first_hjd=data_file.hjd,
                    is_main=True,
                )
                if not dry_run:
                    obj.save()
                    obj.observation_run.add(observation_run)
                    obj.datafiles.add(data_file)
                    obj.save()

                    #   Verify star classification: if classified as 'ST', perform extended search
                    #   to check if it should actually be a cluster, nebula, or galaxy
                    #   Skip this check if a Solar System object was detected
                    verification_updated = False
                    if not solar_system_detected and object_type == 'ST':
                        try:
                            # Check if extended search is enabled (can be disabled via environment variable)
                            enable_extended = str(os.environ.get('ENABLE_STAR_VERIFICATION', 'true')).lower() in ('true', '1', 'yes')
                            if enable_extended:
                                verification_result = verify_star_classification(obj, data_file=data_file, enable_extended_search=True)
                                if verification_result['updated']:
                                    verification_updated = True
                                    if print_to_terminal:
                                        best_match = verification_result.get('best_match', {})
                                        logger.info(
                                            f'Star classification corrected for {obj.name}: '
                                            f'now classified as {obj.object_type} '
                                            f'(found: {best_match.get("name", "Unknown")})'
                                        )
                                    # Update object_type variable for consistency
                                    obj.refresh_from_db()
                                    object_type = obj.object_type
                        except Exception as e:
                            # Don't fail object creation if verification fails
                            logger.warning(f'Error during star classification verification for {obj.name}: {e}')

                    #   Handle Solar System objects: add header name as identifier and update main_target
                    if solar_system_detected:
                        # Add header name as an alias if different from detected object name
                        if target and target.lower() != object_name.lower():
                            try:
                                existing_header_id = obj.identifier_set.filter(name__exact=target, info_from_header=True).first()
                                if not existing_header_id:
                                    obj.identifier_set.create(
                                        name=target,
                                        info_from_header=True,
                                    )
                            except Exception as e:
                                logger.debug(f'Error adding header identifier for Solar System object: {e}')
                        
                        # Update datafile target name to match detected Solar System object
                        if should_allow_auto_update(data_file, 'main_target'):
                            data_file.main_target = object_name
                            data_file.save()
                    
                    #   Set alias names (only if verification didn't already update identifiers)
                    elif object_simbad_resolved and not verification_updated:
                        #   Add header name as an alias
                        obj.identifier_set.create(
                            name=target,
                            info_from_header=True,
                        )

                        #   Get aliases from Simbad
                        aliases_field = None
                        try:
                            aliases_field = object_data_table['IDS']
                        except Exception:
                            try:
                                aliases_field = object_data_table['ids']
                            except Exception:
                                aliases_field = None
                        aliases = [] if aliases_field is None else str(aliases_field).split('|')
                        # print(aliases)

                        #   Create Simbad link
                        sanitized_name = object_name.replace(" ", "") \
                            .replace('+', "%2B")
                        simbad_href = f"https://simbad.u-strasbg.fr/" \
                                      f"simbad/sim-id?Ident=" \
                                      f"{sanitized_name}"

                        #   Set identifier objects
                        for alias in aliases:
                            obj.identifier_set.create(
                                name=alias,
                                href=simbad_href,
                            )

                        #   Set datafile target name to Simbad resolved name
                        if should_allow_auto_update(data_file, 'main_target'):
                            data_file.main_target = object_name
                            data_file.save()
                    elif verification_updated:
                        # If verification updated the object, ensure header name is added as identifier
                        # (it might have been removed when identifiers were replaced)
                        try:
                            existing_header_id = obj.identifier_set.filter(name__exact=target, info_from_header=True).first()
                            if not existing_header_id:
                                obj.identifier_set.create(
                                    name=target,
                                    info_from_header=True,
                                )
                        except Exception as e:
                            logger.debug(f'Error adding header identifier after verification: {e}')
                        
                        # Update datafile target name to match updated object name
                        obj.refresh_from_db()
                        if should_allow_auto_update(data_file, 'main_target'):
                            data_file.main_target = obj.name
                            data_file.save()
                    
                    #   Automatically update photometry/spectroscopy flags for object and observation run
                    update_object_photometry_spectroscopy(obj)
                    update_observation_run_photometry_spectroscopy(observation_run)
                
                return {'status': 'new_object_created', 'new_object': obj}
        
            # No object found or matched (within the if block)
            return {'status': 'no_match'}
        except Exception as e:
            # Log the error for debugging
            logger.error(f'Error in evaluate_data_file (within if block) for data_file {data_file.pk} (target: {target}, expo_type: {expo_type}): {e}', exc_info=True)
            return {
                'status': 'error',
                'error': str(e),
                'data_file_pk': data_file.pk,
                'target': target,
                'expo_type': expo_type
            }
    else:
        # Conditions not met for object association
        # Log why we're skipping (for debugging)
        reasons = []
        if target_lower == '' or target_lower == 'unknown':
            reasons.append('empty_or_unknown_target')
        if expo_type != 'LI':
            reasons.append(f'wrong_exposure_type_{expo_type}')
        if 'flat' in target_lower or 'dark' in target_lower:
            reasons.append('flat_or_dark')
        if lookup_ra == -1 or lookup_ra is None or lookup_ra == 0.:
            reasons.append('invalid_ra')
        if lookup_dec == -1 or lookup_dec is None or lookup_dec == 0.:
            reasons.append('invalid_dec')
        
        logger.debug(f'DataFile {data_file.pk} skipped object association: {", ".join(reasons)}')
        return {'status': 'no_match', 'reason': 'conditions_not_met', 'details': reasons}


def analyze_and_update_exposure_type(file_path, plot_histogram=False,
                                     print_to_terminal=False):
    """
    Estimate exposure type (bias, dark, flat, light) and observation type
    (photometry, spectroscopy)

    Parameters
    ----------
    file_path               : `pathlib.Path`
        Path to the file to be analyzed

    plot_histogram          : `boolean`, optional
        If True the histogram of the image will be plotted.

    print_to_terminal       : `boolean`, optional
        If True information will be printed to the terminal.
        Default is ``False``.

    Returns
    -------
                            : `boolean`
        True if image and spectrum type were estimated.

    image_type_fits         : `string`
        Image type from FITS header.

    estimated_image_type    : `string`
        Estimated image type

    spectrum_type           : `string`
        Spectrum type. None for photometric observations.

    instrument              : `string`
        Instrument from FITS header
    """

    jd_start_stf8300 = Time('2015-02-01T00:00:00.00', format='fits').jd

    suffix = file_path.suffix
    if suffix in ['.fit', '.fits', '.FIT', '.FITS']:
        if print_to_terminal:
            print('File: ', file_path.absolute())

        # Tolerate FITS without SIMPLE card to avoid noisy logs
        header = fits.getheader(file_path, 0, ignore_missing_simple=True)

        image_type_fits = header.get('IMAGETYP', 'UK')
        if image_type_fits == 'Flat Field':
            image_type_fits = 'flat'
        if image_type_fits == 'Dark Frame':
            image_type_fits = 'dark'
        if image_type_fits == 'Light Frame':
            image_type_fits = 'light'
        if image_type_fits == 'Bias Frame':
            image_type_fits = 'bias'
        objectname = header.get('OBJECT', 'UK')
        exptime = header.get('EXPTIME', -1)
        instrument = header.get('INSTRUME', '-')
        naxis1 = header.get('NAXIS1', 1)
        binning = header.get('XBINNING', 1)
        # img_filter = header.get('FILTER', '-')
        obs_time = header.get('DATE-OBS', '2000-01-01T00:00:00.00')
        jd = Time(obs_time, format='fits').jd
        rgb = header.get('BAYERPAT', None)

        n_pix_x = naxis1 * binning

        image_data_original = fits.getdata(file_path, 0, ignore_missing_simple=True)

        img_shape = image_data_original.shape
        # print(image_data_original.shape)
        # print(image_data_original.ndim)

        if image_data_original.ndim != 2:
            return False, None, None, None, None

        image_data = ndimage.median_filter(image_data_original, size=10)

        if plot_histogram:
            plt.figure(figsize=(20, 7))
            ax1 = plt.subplot(1, 2, 1)
            ax2 = plt.subplot(1, 2, 2)
            # ax = fig.add_subplot(1, 1, 1)

            ax1.hist(image_data.flatten(), bins='auto')
            # plt.show()

            # plt.imshow(image_data, cmap='gray', vmin=2.6E3, vmax=3E3)
            norm = simple_norm(image_data, 'log')
            ax2.imshow(image_data, cmap='gray', origin='lower', norm=norm)
            # ax2.colorbar()
            plt.show()
            plt.close()

        histogram = ndimage.histogram(image_data, 0, 65000, 600)
        max_histo_id = np.argmax(histogram)
        n_non_zero_histo = len(np.nonzero(histogram)[0])

        median = np.median(image_data)
        mean = np.mean(image_data)
        variance = np.var(image_data)
        standard = np.std(image_data)

        y_sum = np.sum(image_data_original, axis=1)
        y_mean = np.mean(image_data_original, axis=1)
        # print(dir(image_data_original))
        # print(image_data_original.shape)
        # print(len(y_sum))
        # print(y_sum)

        id_y_mean_mid = int(len(y_mean) * 0.5)
        y_mid_mean_value = y_mean[id_y_mean_mid]
        print('y_mid_mean_value =', y_mid_mean_value)

        y_sum_min = np.min(y_sum)
        # y_sum_mean = np.mean(y_sum)
        # y_sum_mean = np.mean(y_sum-y_sum_min)
        y_sum_median = np.median(y_sum - y_sum_min)
        # y_sum_standard = np.std(y_sum)

        # print(y_sum_mean)
        # print(y_sum_median)
        # print(y_sum_standard)
        # print(y_sum_min)
        # print(
        #     # signal.find_peaks(y_sum, height=y_sum_mean, width=15)
        #     # signal.find_peaks(y_sum-y_sum_min, height=y_sum_mean, width=15)
        #     # signal.find_peaks(y_sum-y_sum_min, height=y_sum_median, width=15)
        #     # signal.find_peaks(y_sum, height=y_sum_min, width=15, rel_height=0.9)
        # signal.find_peaks(y_sum-y_sum_min, height=y_sum_median, width=130, rel_height=0.9)
        # )

        # x_sum = np.sum(image_data_original, axis=0)
        # x_sum_min = np.min(x_sum)
        # x_sum_median = np.median(x_sum-x_sum_min)
        # x_sum_standard = np.std(x_sum)

        spectrum_type = None
        flux_in_orders_average = None

        if (instrument != 'SBIG STF-8300'
                and n_pix_x < 9000
                and not (instrument in ['SBIG ST-8 3 CCD Camera', 'SBIG ST-8'] and jd < jd_start_stf8300)):

            einstein_spectra_broad = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                # height=y_sum_mean,
                width=(1110, 1130),
                # rel_height=0.5,
            )
            print('einstein_spectra_broad:')
            print(einstein_spectra_broad)
            einstein_spectra_narrow = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                # height=y_sum_mean,
                width=(775, 795),
                # rel_height=0.5,
            )
            print('einstein_spectra_narrow:')
            print(einstein_spectra_narrow)

            einstein_spectra_half = signal.find_peaks(
                y_sum - y_sum_min,
                height=y_sum_median,
                width=(370, 385),
            )
            print('einstein_spectra_half:')
            print(einstein_spectra_half)

            # print(
            #     signal.find_peaks(
            #         y_sum,
            #         # y_sum-y_sum_min,
            #         height=y_sum_standard,
            #         # width=(110, 160),
            #         # width=110,
            #         width=(130, 190),
            #         # rel_height=0.9,
            #         rel_height=1.0,
            #         distance=4.,
            #         )
            # )
            # print(
            #     signal.find_peaks(
            #         # x_sum-x_sum_min,
            #         x_sum,
            #         height=x_sum_standard,
            #         width=int(naxis1 * 0.5),
            #         rel_height=0.9,
            #         )
            # )
            # print('======')
            # print(
            #     signal.find_peaks(
            #         y_sum-y_sum_min,
            #         height=y_sum_median,
            #         # height=y_sum_mean,
            #         width=(1110, 1130),
            #         # rel_height=0.5,
            #         )
            # )
            if (einstein_spectra_broad[0].size >= 1
                    or einstein_spectra_narrow[0].size >= 1
                    or einstein_spectra_half[0].size == 2):
                spectrum_type = 'einstein'
                # print(dados_spectra)
            else:
                dados_spectra = signal.find_peaks(
                    y_sum - y_sum_min,
                    height=y_sum_median,
                    # height=y_sum_mean,
                    width=(132, 139),
                    rel_height=0.9,
                    prominence=30000.,
                )
                print('dados_spectra:')
                print(dados_spectra)

                dados_peaks = signal.find_peaks(
                    y_sum - y_sum_min,
                    height=y_sum_median,
                    # height=y_sum_mean,
                    # width=(110, 160),
                    # width=110,
                    width=(10, 50),
                    # width=(130, 190),
                    # width=(132, 139),
                    rel_height=0.9,
                    # rel_height=0.9,
                    # rel_height=1.0,
                )
                print('dados_peaks:')
                print(dados_peaks)
                spectrum_detected = False
                if 1 < dados_peaks[0].size < 16:
                    smallest_peak = np.min(dados_peaks[1]['peak_heights'])
                    largest_peak = np.max(dados_peaks[1]['peak_heights'])
                    if largest_peak > 5 * smallest_peak:
                        spectrum_detected = True

                if (dados_spectra[0].size > 1 or
                        (instrument == 'SBIG ST-7' and dados_spectra[0].size) or
                        (instrument in ['SBIG ST-7', 'SBIG ST-8 3 CCD Camera', 'SBIG ST-8']
                         and spectrum_detected)):
                    spectrum_type = 'dados'
                    # print(dados_spectra)
                else:
                    # print(
                    #     signal.find_peaks(
                    #         y_sum-y_sum_min,
                    #         height=y_sum_median,
                    #         # height=y_sum_mean,
                    #         # width=(110, 160),
                    #         # width=110,
                    #         width=(100, 150),
                    #         # width=(132, 139),
                    #         rel_height=0.9,
                    #         # rel_height=1.0,
                    #         )
                    # )

                    baches_spectra = signal.find_peaks(
                        y_sum - y_sum_min,
                        height=y_sum_median,
                        # width=(16, 30),
                        width=(16, 50),
                        # rel_height=0.9,
                        # prominence=30000.,
                        prominence=10000.,
                    )

                    n_order = baches_spectra[0].size

                    jd_pre_baches = Time(
                        '2014-12-08T00:00:00.00',
                        format='fits'
                    ).jd
                    if n_order >= 4 and jd > jd_pre_baches:
                        spectrum_type = 'baches'
                        print('baches_spectra:')
                        print(baches_spectra)
                        # print(baches_spectra[-1])
                        # print(baches_spectra[-1]['right_ips'])

                        x_sum_order = 0.
                        n_pixel_in_orders = 0
                        for i in range(0, n_order):
                            start_order = int(baches_spectra[-1]['left_ips'][i])
                            end_order = int(baches_spectra[-1]['right_ips'][i])

                            x_sum_order += np.sum(
                                image_data_original[start_order:end_order, :]
                            )
                            n_pixel_in_orders += ((end_order - start_order)
                                                  * img_shape[1])

                        flux_in_orders_average = x_sum_order / n_pixel_in_orders
                        print(flux_in_orders_average, n_pixel_in_orders)

        estimated_image_type = 'UK'

        if np.isnan(median) or int(median) == 65535:
            estimated_image_type = 'over_exposed'

        elif (n_non_zero_histo <= 2 and
              standard < 15 and
              # not (instrument == 'QHYCCD-Cameras-Capture' and median > 50) and
              spectrum_type is None):
            # print('exptime', exptime)
            if exptime <= 0.01:
                estimated_image_type = 'bias'
            else:
                estimated_image_type = 'dark'

        elif instrument == 'SBIG ST-i CCD Camera':
            estimated_image_type = 'light'

        elif spectrum_type == 'dados':
            if instrument == 'SBIG ST-7':
                if n_non_zero_histo >= 350:
                    if standard > 11000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'light'
                elif n_non_zero_histo >= 90:
                    if median > 600:
                        estimated_image_type = 'wave'
                    else:
                        estimated_image_type = 'light'
                else:
                    if standard > 670:
                        estimated_image_type = 'light'
                    else:
                        estimated_image_type = 'wave'

            else:
                if n_non_zero_histo >= 300:
                    if standard > 10000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'light'
                elif (n_non_zero_histo >= 100 and
                      600 < standard < 1900):
                    estimated_image_type = 'wave'

                elif n_non_zero_histo > 60:
                    if standard < 220:
                        estimated_image_type = 'light'
                    elif 700 < standard > 6000:
                        estimated_image_type = 'flat'
                    else:
                        estimated_image_type = 'wave'

                elif n_non_zero_histo > 40 and standard > 6000:
                    estimated_image_type = 'flat'

                elif n_non_zero_histo > 35 and standard > 280:
                    estimated_image_type = 'wave'

                else:
                    estimated_image_type = 'light'

        elif spectrum_type == 'baches':
            if (n_non_zero_histo >= 110 and
                    300 < standard < 1500):
                estimated_image_type = 'wave'

            # elif n_non_zero_histo > 60:
            elif n_non_zero_histo > 40:
                if median > 4000 or flux_in_orders_average > 1900:
                    # max_histo_id == 7 and
                    estimated_image_type = 'flat'
                else:
                    estimated_image_type = 'light'

            elif n_non_zero_histo >= 25:
                if standard > 550:
                    # max_histo_id == 7 and
                    estimated_image_type = 'flat'
                else:
                    estimated_image_type = 'light'

            else:
                estimated_image_type = 'light'

        elif spectrum_type == 'einstein':
            estimated_image_type = 'light'

        else:
            if rgb is not None:
                estimated_image_type = 'rgb'

            if standard > 1000:
                if n_non_zero_histo > 100 and y_mid_mean_value < 10000:
                    estimated_image_type = 'light'
                else:
                    estimated_image_type = 'flat'

            elif standard <= 200 and max_histo_id < 100:
                estimated_image_type = 'light'

            elif (standard > 300 and
                  100 > max_histo_id > 20):
                estimated_image_type = 'flat'

            elif (200 < standard < 500 and
                  n_non_zero_histo > 100):
                estimated_image_type = 'light'

            elif y_mid_mean_value > 10000:
                estimated_image_type = 'flat'

        if print_to_terminal:
            print('Object name: ', objectname)
            print(
                'Image type: ',
                image_type_fits,
                '\tEstimated: ',
                estimated_image_type,
                '\tSpectra type: ',
                spectrum_type,
                '\tInstrument: ',
                instrument,
            )
            # print(histogram)
            print(
                'Histo max position: ',
                max_histo_id,
                '\tNumber of non zero bins: ',
                n_non_zero_histo,
                # np.nonzero(histogram),
                # len(histogram),
                '\tAverage flux in orders: ',
                flux_in_orders_average,
            )
            print(
                'Median = ',
                median,
                '\tMean = ',
                mean,
                '\tVariance = ',
                variance,
                '\tStandard deviation = ',
                standard,
            )
            print()

        return True, image_type_fits, estimated_image_type, spectrum_type, instrument
    else:
        return False, None, None, None, None
