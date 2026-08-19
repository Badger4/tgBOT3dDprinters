"""
Bambu Lab HMS (Health Management System) error code decoder.
Converts raw bit-packed HMS payloads into human-readable Ukrainian error descriptions.
"""

from typing import Any

# Common Bambu Lab HMS error codes mapped to Ukrainian descriptions
HMS_CODE_MAP: dict[str, str] = {
    # Extruder & Filament errors
    "HMS_0300_0800_0001_0001": "Застрягання нитки або збій датчика екструдера",
    "HMS_0300_0800_0002_0001": "Перевищення температури хотенда / сопла",
    "HMS_0300_0800_0003_0001": "Збій нагрівача сопла або обрив термопари",
    "HMS_0300_0800_0004_0001": "Низька температура сопла під час екструзії",
    # Bed & Motion errors
    "HMS_0300_0100_0001_0001": "Збій вирівнювання столу (Auto Bed Leveling failed)",
    "HMS_0300_0100_0002_0001": "Перевищення температури нагрівача столу",
    "HMS_0300_0200_0001_0001": "Збій резонансного калібрування (Input Shaping / Homing failed)",
    # AI Camera & Safety alerts
    "HMS_0300_0A00_0001_0001": "AI-детекція 'спагеті' виявила дефект друку",
    "HMS_0300_0B00_0001_0001": "Інспекція першого шару виявила відхилення",
    "HMS_0300_0C00_0001_0001": "Двері камери або передня кришка відчинені",
    # AMS System errors
    "HMS_0500_0100_0001_0001": "Збій подачі нитки в моторі AMS",
    "HMS_0500_0200_0001_0001": "Збій RFID-зчитувача AMS",
    "HMS_0500_0300_0001_0001": "Нитка AMS закінчилась або не змогла висунутись",
    "HMS_0500_0400_0001_0001": "Застрягання нитки в трубці PTFE AMS",
}


def decode_hms_entry(entry: dict[str, Any] | int | str) -> str:
    """
    Decodes a single HMS error entry into a formatted string with description.
    Supports raw integer masks, string codes, or dicts containing 'code' and 'attr'.
    """
    if isinstance(entry, dict):
        raw_code = entry.get("code")
        raw_attr = entry.get("attr")
        if isinstance(raw_code, int) and isinstance(raw_attr, int):
            code_hex = f"{raw_code:08X}"
            attr_hex = f"{raw_attr:08X}"
            code_str = f"HMS_{code_hex[:4]}_{code_hex[4:]}_{attr_hex[:4]}_{attr_hex[4:]}"
        else:
            code_str = str(entry.get("code") or entry)
    elif isinstance(entry, int):
        code_hex = f"{entry:08X}"
        code_str = f"HMS_{code_hex[:4]}_{code_hex[4:]}_0001_0001"
    else:
        code_str = str(entry)

    desc = HMS_CODE_MAP.get(code_str.upper())
    if desc:
        return f"{code_str}: {desc}"
    return code_str


def format_hms_errors(hms_list: list[Any]) -> list[str]:
    """Converts a list of raw HMS error entries into human-readable descriptions."""
    if not hms_list or not isinstance(hms_list, list):
        return []
    resolved: list[str] = []
    for entry in hms_list:
        decoded = decode_hms_entry(entry)
        if decoded and decoded not in resolved:
            resolved.append(decoded)
    return resolved
