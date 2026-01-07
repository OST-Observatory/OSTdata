"""
Utility functions for instrument and telescope name normalization.
Moved from objects/api/serializers.py for reuse across apps.
"""

# Simple alias maps to normalize common instrument/telescope names
INSTRUMENT_ALIASES = {
    'sbig st-8 3 ccd camera': 'ST-8',
    'sbig st-8': 'ST-8',
    'sbig st8': 'ST-8',
    'st-8': 'ST-8',
    'st8': 'ST-8',
    'QHYCCD-Cameras-Capture': 'QHY600M or QHY268M',
    'QHY600M': 'QHY600M',
    'QHY268M': 'QHY268M',
    'QHY600': 'QHY600M',
    'QHY268': 'QHY268M',
    'SBIG ST-i CCD Camera': 'ST-i',
    'SBIG ST-i': 'ST-i',
    'SBIG ST-i CCD': 'ST-i',
}

TELESCOPE_ALIASES = {
    'meade lx200': 'LX200',
    'lx200': 'LX200',
    'sky-watcher': 'SkyWatcher',
    'Planewave CDK20': 'CDK20',
}

# Normalize alias maps to lowercase keys for robust, case-insensitive lookup
INSTRUMENT_ALIASES = { (k.strip().lower() if isinstance(k, str) else k): v for k, v in INSTRUMENT_ALIASES.items() }
TELESCOPE_ALIASES  = { (k.strip().lower() if isinstance(k, str) else k): v for k, v in TELESCOPE_ALIASES.items() }


def normalize_alias(name: str, aliases: dict) -> str:
    """
    Normalize a name using an alias map.
    
    Args:
        name: The name to normalize
        aliases: Dictionary mapping lowercase keys to normalized values
        
    Returns:
        Normalized name if found in aliases, otherwise original name
    """
    if not name:
        return name
    key = str(name).strip().lower()
    return aliases.get(key, name)


def normalize_instrument(name: str) -> str:
    """
    Normalize instrument name using INSTRUMENT_ALIASES.
    
    Args:
        name: Instrument name to normalize
        
    Returns:
        Normalized instrument name
    """
    return normalize_alias(name, INSTRUMENT_ALIASES)


def normalize_telescope(name: str) -> str:
    """
    Normalize telescope name using TELESCOPE_ALIASES.
    
    Args:
        name: Telescope name to normalize
        
    Returns:
        Normalized telescope name
    """
    return normalize_alias(name, TELESCOPE_ALIASES)

