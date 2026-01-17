"""
Utility functions for instrument and telescope name normalization.
Moved from objects/api/serializers.py for reuse across apps.
Also includes override flag management functions.
"""

# Simple alias maps to normalize common instrument/telescope names
INSTRUMENT_ALIASES = {
    'SBIG ST-i CCD Camera': 'SBIG ST-i',
    'SBIG ST-i': 'SBIG ST-i',
    'SBIG ST-i CCD': 'SBIG ST-i',
    'SBIG ST-7': 'SBIG ST-7',
    'ST-7': 'SBIG ST-7',
    'sbig st-8 3 ccd camera': 'SBIG ST-8',
    'sbig st-8': 'SBIG ST-8',
    'sbig st8': 'SBIG ST-8',
    'st-8': 'SBIG ST-8',
    'st8': 'SBIG ST-8',
    'SBIG STF-8300 CCD Camera': 'SBIG STF-8300',
    'SBIG STF-8300': 'SBIG STF-8300',
    'QHYCCD-Cameras-Capture': 'QHY 600M or QHY 268M',
    'QHY600M': 'QHY 600M',
    'QHY600': 'QHY 600M',
    'QHY CCD QHY600M-3eda8b4': 'QHY 600M',
    'QHY CCD QHY600M-62e19d4': 'QHY 600M',
    'QHY268': 'QHY 268M',
    'QHY268M': 'QHY 268M',
    'QHY CCD QHY268M-92149f4': 'QHY 268M',
    'QHY CCD QHY5III485C-131': 'QHY 5III485C',
    'QHY CCD QHY5III485C-131e734a8677559cd': 'QHY 5III485C',
    'QHY CCD QHY5III462C-888': 'QHY 5III462C',
    'QHY CCD QHY5III462C-888c314299c69d610': 'QHY 5III462C',
    'ZWO ASI2600MC Pro': 'ZWO ASI2600MC Pro',
    'ZWO ASI2600MC Pro(2600)': 'ZWO ASI2600MC Pro',
    'ZWO CCD ASI2600MC Pro(2600)': 'ZWO ASI2600MC Pro',
    'ZWO ASI294MM Pro': 'ZWO ASI294MM Pro',
    'ZWO CCD ASI294MM Pro': 'ZWO ASI294MM Pro',
    'ASI174MM': 'ZWO ASI174MM',
    'ZWO ASI174MM': 'ZWO ASI174MM',
    'ASI220MM': 'ZWO ASI220MM',
    'ZWO ASI220MM': 'ZWO ASI220MM',
    'ASI678MM': 'ZWO ASI678MM',
    'ZWO ASI678MM': 'ZWO ASI678MM',
    'Skyris 445C': 'Skyris 445C',
}

TELESCOPE_ALIASES = {
    'meade lx200': 'LX200',
    'lx200': 'LX200',
    'sky-watcher': 'SkyWatcher',
    'Planewave CDK20': 'CDK20',
}

# Instrument catalog with pixel dimensions for detection and API endpoints
INSTRUMENT_CATALOG = [
    { 'name': 'QHY 600M', 'px_um': 3.76, 'w': 9576, 'h': 6388, 'w_alt': 9600, 'h_alt': 6422 },
    { 'name': 'QHY 268M', 'px_um': 3.76, 'w': 6252, 'h': 4176, 'w_alt': 6280, 'h_alt': 4210 },
    { 'name': 'QHY 5III485C', 'px_um': 2.90, 'w': 3864, 'h': 2180 },
    { 'name': 'QHY 5III462C', 'px_um': 2.90, 'w': 1920, 'h': 1080 },
    { 'name': 'SBIG ST8',     'px_um': 9.00, 'w': 1530, 'h': 1020 },
    { 'name': 'SBIG ST7',     'px_um': 9.00, 'w': 765,  'h': 510  },
    { 'name': 'SBIG STF-8300M','px_um': 5.40,'w': 3326, 'h': 2504 },
    { 'name': 'SBIG ST-i',    'px_um': 7.40, 'w': 648,  'h': 486  },
    { 'name': 'Skyris 445C', 'px_um': 3.75, 'w': 1280, 'h': 960 },
    { 'name': 'ZWO ASI174MM', 'px_um': 5.86, 'w': 1936, 'h': 1216 },
    { 'name': 'ZWO ASI220MM', 'px_um': 4.00, 'w': 1920, 'h': 1080 },
    { 'name': 'ZWO ASI678MM', 'px_um': 2.00, 'w': 3840, 'h': 2160 },
    { 'name': 'ZWO ASI2600MC Pro', 'px_um': 3.76, 'w': 6248, 'h': 4176 },
    { 'name': 'ZWO ASI294MM Pro', 'px_um': 2.3, 'w': 8288, 'h': 5644 }
]

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


# Override flag management functions

def get_override_field_name(field_name: str) -> str:
    """
    Get the override flag field name for a given field.
    
    Args:
        field_name: Name of the field to get override flag for
        
    Returns:
        Name of the override flag field (e.g., 'name_override' for 'name')
    """
    return f"{field_name}_override"


def should_allow_auto_update(model_instance, field_name: str) -> bool:
    """
    Check if automatic update is allowed for a field (override flag not set).
    
    Args:
        model_instance: Django model instance
        field_name: Name of the field to check
        
    Returns:
        True if automatic update is allowed (override flag is False or doesn't exist),
        False if override flag is set to True
    """
    override_field_name = get_override_field_name(field_name)
    if hasattr(model_instance, override_field_name):
        return not getattr(model_instance, override_field_name, False)
    # If override field doesn't exist, allow update (backward compatibility)
    return True


def check_and_set_override(model_instance, field_name: str, new_value, old_value=None) -> bool:
    """
    Check if a field value changed and set the override flag if it did.
    Only sets the flag if the value actually changed.
    
    Args:
        model_instance: Django model instance
        field_name: Name of the field that was changed
        new_value: New value for the field
        old_value: Old value (if None, will be read from instance)
        
    Returns:
        True if override flag was set, False otherwise
    """
    override_field_name = get_override_field_name(field_name)
    if not hasattr(model_instance, override_field_name):
        return False
    
    # Get old value if not provided
    if old_value is None:
        old_value = getattr(model_instance, field_name, None)
    
    # Check if value actually changed
    if old_value == new_value:
        return False
    
    # Set override flag
    setattr(model_instance, override_field_name, True)
    return True


def was_manually_changed(instance, field_name: str) -> bool:
    """
    Check if a field was last changed by a user (not a task) using HistoricalRecords.
    
    Args:
        instance: Django model instance with HistoricalRecords
        field_name: Name of the field to check
        
    Returns:
        True if the field was last changed by a user (history_user is not None),
        False otherwise
    """
    if not hasattr(instance, 'history'):
        return False
    
    try:
        # Get the most recent history entry
        latest_history = instance.history.order_by('-history_date').first()
        if not latest_history:
            return False
        
        # Check if history_user is set (indicates user change, not task)
        return latest_history.history_user is not None
    except Exception:
        return False


def detect_user_changes_from_history(instance) -> list:
    """
    Analyze history and return list of fields that were changed by users.
    
    Args:
        instance: Django model instance with HistoricalRecords
        
    Returns:
        List of field names that were changed by users
    """
    changed_fields = []
    if not hasattr(instance, 'history'):
        return changed_fields
    
    try:
        # Get all history entries ordered by date
        history_entries = instance.history.order_by('history_date').all()
        if len(history_entries) < 2:
            return changed_fields
        
        # Compare consecutive entries to find user changes
        for i in range(1, len(history_entries)):
            current = history_entries[i]
            previous = history_entries[i-1]
            
            # Only consider entries with history_user set (user changes)
            if current.history_user is None:
                continue
            
            # Compare all fields to find changes
            for field in instance._meta.get_fields():
                if field.name in ['id', 'history_id', 'history_date', 'history_user', 'history_type']:
                    continue
                if hasattr(field, 'attname'):
                    field_name = field.attname
                else:
                    field_name = field.name
                
                try:
                    current_value = getattr(current, field_name, None)
                    previous_value = getattr(previous, field_name, None)
                    
                    if current_value != previous_value:
                        # Get the base field name (without _id suffix for ForeignKeys)
                        base_field_name = field_name.replace('_id', '')
                        if base_field_name not in changed_fields:
                            changed_fields.append(base_field_name)
                except Exception:
                    continue
        
        return changed_fields
    except Exception:
        return changed_fields

