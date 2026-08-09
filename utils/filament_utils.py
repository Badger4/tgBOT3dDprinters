"""
Utility functions for parsing filament type and AMS slot keys.
"""
import re
from models.enums import AMSSlot

KNOWN_FILAMENT_TYPES = [
    "PLA+", "PLA-CF", "PLA", "PETG-CF", "PETG", "PET",
    "ABS-GF", "ABS", "ASA", "TPU-95A", "TPU",
    "PPA-CF", "PA-CF", "PA6-CF", "PA", "PC", "HIPS", "PVA"
]

def parse_slot_key_from_text(text: str) -> str:
    """Parses text like 'A1', 'Slot 2', 'зовнішній' into canonical AMS slot ID string."""
    clean = text.lower()
    if "a1" in clean or "slot 1" in clean:
        return AMSSlot.A1.value
    elif "a2" in clean or "slot 2" in clean:
        return AMSSlot.A2.value
    elif "a3" in clean or "slot 3" in clean:
        return AMSSlot.A3.value
    elif "a4" in clean or "slot 4" in clean:
        return AMSSlot.A4.value
    elif "зовнішн" in clean or "vt" in clean or "external" in clean:
        return AMSSlot.EXTERNAL.value
    return AMSSlot.A1.value

def extract_filament_type_from_name(name: str) -> str:
    """Extracts known filament type string from a filename or preset name."""
    if not name:
        return "PLA"
    name_upper = name.upper()
    for f_type in KNOWN_FILAMENT_TYPES:
        pattern = r'(?:\b|_)' + re.escape(f_type) + r'(?:\b|_)'
        if re.search(pattern, name_upper):
            return f_type
    words = name.strip().split()
    return words[0] if words else name.strip()
