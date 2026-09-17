"""
Utility functions for parsing filament type and AMS slot keys.
"""

from __future__ import annotations

import re
from typing import Any

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

# Extended color mappings for 60+ 3D printing filament colors and synonyms
# Format: (search_patterns, emoji, hex_code, uk_display_name, en_display_name)
EXTENDED_COLOR_MAP: list[tuple[list[str], str, str, str, str]] = [
    # Бірюзовий / Teal / Turquoise / Cyan / Аква / Морська хвиля
    (["бірюз", "бирюз", "turquoise", "teal", "морськ", "тиффані", "тиффани", "tiffany"], "🩵", "#0D9488", "Бірюзовий", "Turquoise"),
    (["аква", "aqua", "cyan"], "🩵", "#06B6D4", "Аква", "Aqua"),
    (["блакитн", "голуб", "небесн", "azure", "sky blue"], "🩵", "#38BDF8", "Блакитний", "Sky Blue"),

    # Синій / Blue / Navy / Індиго
    (["темно-синій", "темно синій", "темно-синий", "navy"], "🫐", "#1E3A8A", "Темно-синій", "Navy Blue"),
    (["індиго", "indigo"], "🫐", "#4338CA", "Індиго", "Indigo"),
    (["синій", "синий", "blue"], "🔵", "#3B82F6", "Синій", "Blue"),

    # М'ятний / Лайм / Салатовий / Хакі / Олива / Зелений / Смарагдовий
    (["м'ят", "мʼят", "мят", "mint"], "🍃", "#2DD4BF", "М'ятний", "Mint"),
    (["салат", "лайм", "lime"], "🍏", "#84CC16", "Салатовий", "Lime"),
    (["олив", "olive"], "🫒", "#65A30D", "Оливковий", "Olive"),
    (["хакі", "хаки", "khaki"], "🫒", "#556B2F", "Хакі", "Khaki"),
    (["темно-зелен", "темно зелен", "dark green", "хвоя", "лісов"], "🌲", "#065F46", "Темно-зелений", "Dark Green"),
    (["смарагд", "изумруд", "emerald"], "🟢", "#059669", "Смарагдовий", "Emerald"),
    (["зелен", "green"], "🟢", "#10B981", "Зелений", "Green"),

    # Червоний / Red / Бордовий / Вишневий / Кораловий / Рубін
    (["бордо", "burgundy", "maroon", "марсал"], "🍷", "#991B1B", "Бордовий", "Burgundy"),
    (["вишн", "cherry"], "🍒", "#881337", "Вишневий", "Cherry"),
    (["корал", "coral"], "🪸", "#F43F5E", "Кораловий", "Coral"),
    (["рубін", "рубин", "ruby"], "🔴", "#BE123C", "Рубіновий", "Ruby"),
    (["червон", "красн", "red"], "🔴", "#EF4444", "Червоний", "Red"),

    # Рожевий / Pink / Малиновий / Фуксія
    (["малин", "raspberry"], "🌺", "#BE185D", "Малиновий", "Raspberry"),
    (["фуксі", "фукси", "fuchsia", "magenta"], "🌸", "#D946EF", "Фуксія", "Fuchsia"),
    (["рожев", "розов", "pink"], "🌸", "#EC4899", "Рожевий", "Pink"),

    # Жовтий / Yellow / Помаранчевий / Персиковий / Теракотовий
    (["лимон", "lemon"], "🍋", "#FACC15", "Лимонний", "Lemon"),
    (["гірчичн", "mustard"], "🌾", "#CA8A04", "Гірчичний", "Mustard"),
    (["жовт", "желт", "yellow"], "🟡", "#FBBF24", "Жовтий", "Yellow"),
    (["персик", "peach"], "🍑", "#FDBA74", "Персиковий", "Peach"),
    (["теракот", "terracotta", "цеглян"], "🧱", "#C2410C", "Теракотовий", "Terracotta"),
    (["помаранч", "оранжев", "orange"], "🟠", "#F97316", "Помаранчевий", "Orange"),

    # Фіолетовий / Purple / Бузковий / Лаванда
    (["бузок", "бузков", "сирен", "lilac"], "🪻", "#C084FC", "Бузковий", "Lilac"),
    (["лаванд", "lavender"], "🪻", "#A855F7", "Лавандовий", "Lavender"),
    (["фіолетов", "фиолетов", "purple", "violet", "пурпур"], "🟣", "#8B5CF6", "Фіолетовий", "Purple"),

    # Коричневий / Brown / Бежевий / Шоколад / Кава
    (["шоколад", "chocolate"], "🍫", "#451A03", "Шоколадний", "Chocolate"),
    (["кав", "кофе", "капучино", "coffee"], "☕", "#5B3A29", "Кавовий", "Coffee"),
    (["коричнев", "коричн", "brown"], "🟤", "#92400E", "Коричневий", "Brown"),
    (["пісок", "пісочн", "песок", "песочн", "sand"], "🏜️", "#E2D9C8", "Пісочний", "Sand"),
    (["бежев", "beige"], "🌾", "#D4B996", "Бежевий", "Beige"),
    (["слонов", "ivory", "кремов", "cream"], "🥛", "#FFFFF0", "Слонова кістка", "Ivory"),

    # Метали: Золото / Срібло / Мідь / Бронза
    (["золот", "золото", "gold"], "🪙", "#EAB308", "Золотий", "Gold"),
    (["мід", "медн", "медь", "copper"], "🥉", "#B45309", "Мідний", "Copper"),
    (["бронз", "bronze"], "🥉", "#CD7F32", "Бронзовий", "Bronze"),
    (["сріб", "серебр", "silver"], "🥈", "#94A3B8", "Срібний", "Silver"),

    # Чорний / Сірий / Графіт / Білий / Прозорий
    (["графіт", "графит", "graphite", "антрацит", "anthracite"], "🖤", "#374151", "Графітовий", "Graphite"),
    (["темно-сір", "темно сір", "dark grey", "dark gray"], "🖤", "#4B5563", "Темно-сірий", "Dark Grey"),
    (["світло-сір", "світло сір", "light grey", "light gray"], "🩶", "#CBD5E1", "Світло-сірий", "Light Grey"),
    (["сірий", "серый", "grey", "gray"], "🩶", "#808080", "Сірий", "Grey"),
    (["чорн", "черн", "black"], "⚫", "#000000", "Чорний", "Black"),
    (["білий", "белый", "white"], "⚪", "#FFFFFF", "Білий", "White"),
    (["прозор", "прозрач", "натуральн", "clear", "transparent", "natural"], "🔘", "#E5E7EB", "Прозорий", "Clear"),
    (["люмінесцент", "glow", "фосфор"], "✨", "#A7F3D0", "Люмінесцентний", "Glow"),
    (["неон", "neon"], "⚡", "#39FF14", "Неоновий", "Neon"),
    (["веселк", "rainbow"], "🌈", "#F43F5E", "Веселка (Rainbow)", "Rainbow"),
]


def get_color_display_name(val: Any, lang: str = "uk") -> str:
    """Returns a user-friendly color name with emoji (e.g. '🩵 Бірюзовий'), avoiding raw hex codes."""
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

    # 1. First priority: if user provided a specific custom color name, preserve it!
    if raw_name:
        clean_name = re.sub(r"^[\s\W]+", "", raw_name).strip()
        if clean_name and clean_name.lower() not in ["кольоровий", "colored", "custom", "none"]:
            # If raw_name already has an emoji at start, preserve as is
            if re.match(r"^[^\w\s#]", raw_name):
                return raw_name
            ico = get_color_emoji(raw_name or raw_hex)
            return f"{ico} {clean_name}"

    # 2. Match by hex if known
    if raw_hex:
        norm_hex = raw_hex.upper()
        if not norm_hex.startswith("#"):
            norm_hex = f"#{norm_hex}"
        for label, hx in color_list:
            if hx.upper() == norm_hex:
                return label
        for patterns, emoji, hx, uk_name, en_name in EXTENDED_COLOR_MAP:
            if hx.upper() == norm_hex:
                name = en_name if lang == "en" else uk_name
                return f"{emoji} {name}"
        ico = get_color_emoji(raw_hex)
        return f"{ico} Кольоровий" if lang != "en" else f"{ico} Colored"

    return "⚪ Білий" if lang != "en" else "⚪ White"


def parse_filament_color(text: str) -> tuple[str, str]:
    """Parses color button text, color name or hex into (hex_code, display_name)."""
    raw = text.strip()
    low = raw.lower()

    # 1. Exact match against base buttons
    for label, hex_code in COLOR_NAMES_UK + COLOR_NAMES_EN:
        clean_label = re.sub(r"[^\w\s]", "", label).strip().lower()
        if label.lower() == low or clean_label == low or hex_code.lower() == low:
            clean_name = re.sub(r"^[\s\W]+", "", label).strip()
            return hex_code, clean_name

    # 2. Direct Hex match
    hex_match = re.search(r"#?([0-9a-fA-F]{6})", raw)
    if hex_match and (raw.startswith("#") or len(raw) == 6):
        hx = f"#{hex_match.group(1).upper()}"
        for label, known_hx in COLOR_NAMES_UK + COLOR_NAMES_EN:
            if known_hx.upper() == hx:
                clean_name = re.sub(r"^[\s\W]+", "", label).strip()
                return hx, clean_name
        for patterns, emoji, known_hx, uk_name, en_name in EXTENDED_COLOR_MAP:
            if known_hx.upper() == hx:
                return hx, uk_name
        return hx, "Користувацький"

    # 3. Match against EXTENDED_COLOR_MAP
    clean_low = re.sub(r"[^\w\s-]", "", low).strip()
    best_match = None
    best_len = 0
    for patterns, emoji, hx, uk_name, en_name in EXTENDED_COLOR_MAP:
        for p in patterns:
            p_low = p.lower()
            if p_low in clean_low:
                if len(p_low) > best_len:
                    best_len = len(p_low)
                    best_match = (hx, uk_name)

    if best_match:
        hx, default_uk_name = best_match
        clean_custom = re.sub(r"^[\s\W]+", "", raw).capitalize()
        words = clean_low.split()
        if len(words) <= 1:
            return hx, default_uk_name
        return hx, clean_custom if clean_custom else default_uk_name

    # 4. Fallback for custom/unrecognized color name (preserves exact name, assigns distinct hash hex)
    clean_custom = re.sub(r"^[\s\W]+", "", raw).capitalize()
    if clean_custom:
        import hashlib
        h = int(hashlib.md5(clean_custom.encode("utf-8")).hexdigest()[:6], 16)
        r = 90 + (h & 0x7F)
        g = 90 + ((h >> 8) & 0x7F)
        b = 90 + ((h >> 16) & 0x7F)
        custom_hx = f"#{r:02X}{g:02X}{b:02X}"
        return custom_hx, clean_custom

    return "#3B82F6", "Синій"


def get_color_emoji(hex_code_or_name: str) -> str:
    """Returns matching emoji for a hex color code, color name, or dictionary."""
    if not hex_code_or_name:
        return "🎨"
    raw = str(hex_code_or_name).strip()
    low = raw.lower()
    code = raw.upper()
    if not code.startswith("#") and len(code) == 6 and re.match(r"^[0-9A-F]{6}$", code):
        code = f"#{code}"

    # Check base lists by hex or label
    for label, hx in COLOR_NAMES_UK:
        clean_label = re.sub(r"[^\w\s]", "", label).strip().lower()
        if hx.upper() == code[:7] or label.lower() in low or clean_label in low:
            return label.split()[0]

    # Check extended map
    clean_low = re.sub(r"[^\w\s-]", "", low).strip()
    for patterns, emoji, hx, uk_name, en_name in EXTENDED_COLOR_MAP:
        if hx.upper() == code[:7] or uk_name.lower() in low or en_name.lower() in low:
            return emoji
        for p in patterns:
            if p.lower() in clean_low:
                return emoji

    return "🎨"


def filter_spool_movements(
    movements: list[dict[str, Any]],
    spool_id: str | None = None,
    action: str | None = None,
    date_range: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Filters movements log by spool, action type, date range, and text query."""
    from datetime import datetime, timedelta

    res = list(movements)

    # 1. Spool ID filter
    if spool_id and str(spool_id).strip() not in ["", "all", "None"]:
        target_s = str(spool_id).strip()
        res = [m for m in res if str(m.get("spool_id", "")).strip() == target_s]

    # 2. Action filter
    if action and str(action).strip() not in ["", "all", "None"]:
        act = str(action).strip().lower()
        if act == "stock":
            res = [m for m in res if str(m.get("action", "")).lower() in ["initial_stock", "refill"]]
        else:
            res = [m for m in res if str(m.get("action", "")).lower() == act]

    # 3. Date range filter
    if date_range and str(date_range).strip() not in ["", "all", "None"]:
        dr = str(date_range).strip().lower()
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day).timestamp()

        if dr == "today":
            res = [m for m in res if float(m.get("timestamp", 0)) >= today_start]
        elif dr == "yesterday":
            yesterday_start = (datetime(now.year, now.month, now.day) - timedelta(days=1)).timestamp()
            res = [m for m in res if yesterday_start <= float(m.get("timestamp", 0)) < today_start]
        elif dr in ["week", "7days", "7d"]:
            week_start = (now - timedelta(days=7)).timestamp()
            res = [m for m in res if float(m.get("timestamp", 0)) >= week_start]
        elif dr in ["month", "30days", "30d"]:
            month_start = (now - timedelta(days=30)).timestamp()
            res = [m for m in res if float(m.get("timestamp", 0)) >= month_start]

    # 4. Text query filter
    if query and str(query).strip():
        q_low = str(query).strip().lower()
        res = [
            m for m in res
            if q_low in str(m.get("spool_name", "")).lower()
            or q_low in str(m.get("reason", "")).lower()
            or q_low in str(m.get("user", "")).lower()
            or q_low in str(m.get("action", "")).lower()
        ]

    return sorted(res, key=lambda x: x.get("timestamp", 0), reverse=True)


