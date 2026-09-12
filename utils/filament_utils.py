"""
Utility functions for parsing filament type and AMS slot keys.
"""

import re

KNOWN_FILAMENT_TYPES = [
    "ASA-AERO",
    "PETG-CF",
    "PLA-AERO",
    "PPA-CF",
    "PPA-GF",
    "TPU-AMS",
    "ABS-GF",
    "ASA-CF",
    "PA6-CF",
    "PLA-CF",
    "PET-CF",
    "PA-GF",
    "PP-CF",
    "PP-GF",
    "PE-CF",
    "PCTG",
    "BVOH",
    "CoPE",
    "HIPS",
    "PA6",
    "PETG",
    "PLA",
    "ABS",
    "TPU",
    "ASA",
    "PVA",
    "SBS",
    "EVA",
    "PHA",
    "PP",
    "PE",
    "PC",
    "PA",
]


def parse_slot_key_from_text(text: str) -> str:
    """Parses text like 'A1', 'Slot 2', 'зовнішній' into canonical AMS slot ID string."""
    from models.enums import AMSSlot

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
        pattern = r"(?:\b|_)" + re.escape(f_type) + r"(?:\b|_)"
        if re.search(pattern, name_upper):
            return f_type
    words = name.strip().split()
    return words[0] if words else name.strip()


COLOR_NAMES_UK = [
    ("⚫ Чорний", "#000000"),
    ("⚪ Білий", "#FFFFFF"),
    ("🩶 Сірий", "#808080"),
    ("🔴 Червоний", "#EF4444"),
    ("🔵 Синій", "#3B82F6"),
    ("🩵 Блакитний", "#06B6D4"),
    ("🟢 Зелений", "#10B981"),
    ("🍏 Салатовий", "#84CC16"),
    ("🟡 Жовтий", "#FBBF24"),
    ("🟠 Помаранчевий", "#F97316"),
    ("🟣 Фіолетовий", "#8B5CF6"),
    ("🌸 Рожевий", "#EC4899"),
    ("🟤 Коричневий", "#92400E"),
    ("🌾 Бежевий", "#D4B996"),
    ("🪙 Золотий", "#EAB308"),
    ("🥈 Срібний", "#94A3B8"),
    ("🔘 Прозорий", "#E5E7EB"),
]

COLOR_NAMES_EN = [
    ("⚫ Black", "#000000"),
    ("⚪ White", "#FFFFFF"),
    ("🩶 Grey", "#808080"),
    ("🔴 Red", "#EF4444"),
    ("🔵 Blue", "#3B82F6"),
    ("🩵 Cyan", "#06B6D4"),
    ("🟢 Green", "#10B981"),
    ("🍏 Lime", "#84CC16"),
    ("🟡 Yellow", "#FBBF24"),
    ("🟠 Orange", "#F97316"),
    ("🟣 Purple", "#8B5CF6"),
    ("🌸 Pink", "#EC4899"),
    ("🟤 Brown", "#92400E"),
    ("🌾 Beige", "#D4B996"),
    ("🪙 Gold", "#EAB308"),
    ("🥈 Silver", "#94A3B8"),
    ("🔘 Clear", "#E5E7EB"),
]


def get_color_display_name(val: Any, lang: str = "uk") -> str:
    """Returns a user-friendly color name with emoji (e.g. '🍏 Салатовий'), avoiding raw hex codes."""
    if not val:
        return "⚪ Білий" if lang != "en" else "⚪ White"

    raw_name = ""
    raw_hex = ""
    if isinstance(val, dict):
        raw_name = str(val.get("color_name") or "").strip()
        raw_hex = str(val.get("color") or "").strip()
    elif isinstance(val, str):
        if val.strip().startswith("#"):
            raw_hex = val.strip()
        else:
            raw_name = val.strip()

    color_list = COLOR_NAMES_EN if lang == "en" else COLOR_NAMES_UK

    # 1. Match by hex if known
    if raw_hex:
        norm_hex = raw_hex.upper()
        if not norm_hex.startswith("#"):
            norm_hex = f"#{norm_hex}"
        for label, hx in color_list:
            if hx.upper() == norm_hex:
                return label

    # 2. Match by text name
    if raw_name:
        low = raw_name.lower()
        for label, hx in color_list:
            clean_label = re.sub(r"[^\w\s]", "", label).strip().lower()
            if label.lower() in low or clean_label in low:
                return label
        ico = get_color_emoji(raw_hex or raw_name)
        clean_custom = re.sub(r"^[\s\W]+", "", raw_name).capitalize()
        return f"{ico} {clean_custom}".strip() if ico else clean_custom

    if raw_hex:
        ico = get_color_emoji(raw_hex)
        return f"{ico} Кольоровий" if lang != "en" else f"{ico} Colored"

    return "⚪ Білий" if lang != "en" else "⚪ White"


def parse_filament_color(text: str) -> tuple[str, str]:
    """Parses color button text, color name or hex into (hex_code, display_name)."""
    raw = text.strip()
    low = raw.lower()

    for label, hex_code in COLOR_NAMES_UK + COLOR_NAMES_EN:
        clean_label = re.sub(r"[^\w\s]", "", label).strip().lower()
        if label.lower() in low or clean_label in low or hex_code.lower() == low:
            clean_name = re.sub(r"^[\s\W]+", "", label).strip()
            return hex_code, clean_name

    hex_match = re.search(r"#?([0-9a-fA-F]{6})", raw)
    if hex_match:
        hx = f"#{hex_match.group(1).upper()}"
        for label, known_hx in COLOR_NAMES_UK:
            if known_hx.upper() == hx:
                clean_name = re.sub(r"^[\s\W]+", "", label).strip()
                return hx, clean_name
        return hx, "Кольоровий"

    clean_custom = re.sub(r"^[\s\W]+", "", raw).capitalize()
    return "#3B82F6", clean_custom if clean_custom else "Синій"


def get_color_emoji(hex_code: str) -> str:
    """Returns matching emoji for a hex color code or color name."""
    if not hex_code:
        return "🎨"
    raw = str(hex_code).strip()
    low = raw.lower()
    code = raw.upper()
    if not code.startswith("#") and len(code) == 6 and re.match(r"^[0-9A-F]{6}$", code):
        code = f"#{code}"

    for label, hx in COLOR_NAMES_UK:
        clean_label = re.sub(r"[^\w\s]", "", label).strip().lower()
        if hx.upper() == code[:7] or label.lower() in low or clean_label in low:
            return label.split()[0]
    return "🎨"
