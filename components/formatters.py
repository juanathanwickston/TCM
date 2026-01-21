"""
Display Formatters
==================
UI-only transformations for folder-derived names.
Does NOT modify stored paths, folder names, keys, or database values.
"""

import re


def format_display_name(raw_name: str) -> str:
    """
    Clean a folder segment for display.
    
    Rules applied in order:
    1. Strip numeric prefixes (01_, 02_, etc.)
    2. Strip leading underscores (_General -> General)
    3. Strip parentheticals (Not Sure (Drop Here) -> Not Sure)
    
    Args:
        raw_name: Raw folder name from filesystem
        
    Returns:
        Cleaned display name
    """
    if not raw_name:
        return raw_name
    
    name = raw_name
    
    # 1. Strip numeric prefixes: 01_, 02_, 03_, etc.
    name = re.sub(r'^\d+_', '', name)
    
    # 2. Strip leading underscores
    name = name.lstrip('_')
    
    # 3. Strip parentheticals and trailing whitespace
    name = re.sub(r'\s*\([^)]*\)\s*$', '', name)
    
    return name.strip()


def format_display_path(raw_path: str) -> str:
    """
    Clean a full path for display.
    
    Applies format_display_name to each segment and joins with spaced separators.
    
    Example:
        HR/_General/01_Onboarding/01_Instructor Led - In Person
        -> HR / General / Onboarding / Instructor Led - In Person
    
    Args:
        raw_path: Raw relative path with / or \\ separators
        
    Returns:
        Cleaned display path with spaced separators
    """
    if not raw_path:
        return raw_path
    
    # Normalize separators
    path = raw_path.replace("\\", "/").strip("/")
    
    # Split, clean each segment, rejoin with spaced separators
    segments = [s for s in path.split("/") if s]
    cleaned = [format_display_name(seg) for seg in segments]
    
    return " / ".join(cleaned)
