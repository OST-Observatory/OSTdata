"""
Utility functions for instrument and telescope name normalization.
Moved from objects/api/serializers.py for reuse across apps.
Also includes override flag management functions.
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

