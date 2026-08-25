"""
Bambu Lab HMS (Health Management System) error code decoder.
Converts raw bit-packed HMS payloads into human-readable Ukrainian error descriptions.
"""

from typing import Any

# Complete Bambu Lab HMS error codes dictionary mapped to Ukrainian descriptions
HMS_CODE_MAP: dict[str, str] = {
    # --- Category 0100: Mainboard (MC), Power Supply & AP System ---
    "HMS_0100_0100_0001_0001": "Перегрів або збій кулера системної плати MC",
    "HMS_0100_0100": "Помилка системної плати MC або кулера охолодження",
    "HMS_0100_0200_0001_0001": "Перевищення допустимої температури плати MC",
    "HMS_0100_0200": "Перегрів плат керування принтера",
    "HMS_0100_0300_0001_0001": "Втрата зв'язку з платою інструменту (TH Board)",
    "HMS_0100_0300": "Збій зв'язку з платою каретки (Toolhead)",
    "HMS_0100_0400_0001_0001": "Падіння напруги або аварія блоку живлення (PSU)",
    "HMS_0100_0400": "Помилка живлення або збій мережі 220V",
    "HMS_0100_0500_0001_0001": "Збій процесорної плати AP або Wi-Fi модуля",
    "HMS_0100_0500": "Помилка системного модуля AP / Wi-Fi",
    "HMS_0100": "Системна помилка материнської плати MC/AP",

    # --- Category 0200: Toolhead Board (TH), Heaters & Chamber Fans ---
    "HMS_0200_0100_0001_0001": "Збій вентилятора охолодження каретки (Toolhead Fan)",
    "HMS_0200_0100": "Помилка вентилятора каретки або плати TH",
    "HMS_0200_0200_0001_0001": "Збій витяжного вентилятора камери (Chamber Fan)",
    "HMS_0200_0200": "Помилка вентилятора камери або вугільного фільтра",
    "HMS_0200_0300_0001_0001": "Збій обдуву моделі (Part Cooling Fan)",
    "HMS_0200_0300": "Помилка вентилятора обдуву виробу",
    "HMS_0200": "Помилка обладнання каретки або вентиляторів",

    # --- Category 0300: Motion, Extruder, Bed & AI Safety ---
    "HMS_0300_0100_0001_0001": "Збій вирівнювання столу (Auto Bed Leveling failed)",
    "HMS_0300_0100_0001_0003": "Помилка датчика вирівнювання столу (Bed Strain Gauge error)",
    "HMS_0300_0100_0002_0001": "Перевищення температури нагрівача столу",
    "HMS_0300_0100": "Помилка калібрування або нагріву столу",
    "HMS_0300_0200_0001_0001": "Збій резонансного калібрування (Input Shaping / Homing failed)",
    "HMS_0300_0200": "Помилка позиціонування (Homing / Resonance error)",
    "HMS_0300_0300_0001_0001": "Увага: Перевірте натяг ременів осі X/Y",
    "HMS_0300_0300": "Помилка натягу ременів або механіки руху",
    "HMS_0300_0400_0001_0001": "Пропуск кроків крокового мотора (Stepper Motor skipped steps)",
    "HMS_0300_0400": "Пропуск кроків моторів по осях X/Y/Z",
    "HMS_0300_0800_0001_0001": "Застрягання нитки або збій датчика екструдера",
    "HMS_0300_0800_0002_0001": "Перевищення температури хотенда / сопла",
    "HMS_0300_0800_0003_0001": "Збій нагрівача сопла або обрив термопари",
    "HMS_0300_0800_0004_0001": "Низька температура сопла під час екструзії",
    "HMS_0300_0800": "Помилка хотенда або екструдера",
    "HMS_0300_0900_0001_0001": "Спрацював датчик закінчення нитки у хотенді",
    "HMS_0300_0900": "Закінчився філамент або обрив нитки",
    "HMS_0300_0A00_0001_0001": "AI-детекція 'спагеті' виявила дефект друку",
    "HMS_0300_0A00": "AI-детекція збоїв друку (Spaghetti Detection)",
    "HMS_0300_0B00_0001_0001": "Інспекція першого шару виявила відхилення",
    "HMS_0300_0B00": "Помилка першого шару (First Layer Inspection)",
    "HMS_0300_0C00_0001_0001": "Двері камери або передня кришка відчинені",
    "HMS_0300_0C00": "Відчинені двері камери або захисна кришка",
    "HMS_0300_0D00_0001_0001": "Маркер будівельної пластини не виявлено",
    "HMS_0300_0D00": "Помилка визначення пластини друку",
    "HMS_0300": "Помилка механіки, екструдера або AI-камери",

    # --- Category 0500: Automated Material System (AMS) ---
    "HMS_0500_0100_0001_0001": "Збій подачі нитки в моторі AMS (Feeder Motor overload)",
    "HMS_0500_0100": "Помилка мотора подачі нитки AMS",
    "HMS_0500_0200_0001_0001": "Збій RFID-зчитувача AMS (RFID Tag Read fail)",
    "HMS_0500_0200": "Помилка RFID-зчитувача AMS",
    "HMS_0500_0300_0001_0001": "Нитка AMS закінчилась або не змогла висунутись",
    "HMS_0500_0300": "Помилка подачі / закінчення нитки AMS",
    "HMS_0500_0400_0001_0001": "Застрягання нитки в трубці PTFE або хабі AMS",
    "HMS_0500_0400": "Застрягання нитки у трубці чи хабі AMS",
    "HMS_0500_0500_0001_0001": "Критична вологість у блоці AMS (Замініть десикант)",
    "HMS_0500_0500": "Попередження про вологість у блоці AMS",
    "HMS_0500_0600_0001_0001": "Перевантаження допоміжного мотора котушки AMS",
    "HMS_0500_0600": "Помилка мотора обертання котушки AMS",
    "HMS_0500": "Помилка модуля або слотів системи AMS",

    # --- Category 0700: Micro Lidar & Optical Calibration ---
    "HMS_0700_0100_0001_0001": "Забруднено лінзу камери Micro Lidar",
    "HMS_0700_0100": "Помилка оптики Micro Lidar (Протріть серветкою)",
    "HMS_0700_0200_0001_0001": "Збій лазерного калібрування потоку (Flow Calibration)",
    "HMS_0700_0200": "Помилка оптичного калібрування потоку Micro Lidar",
    "HMS_0700": "Помилка сенсора Micro Lidar",

    # --- Category 1200: Expansion Modules & External Accessories ---
    "HMS_1200_0100_0001_0001": "Помилка зовнішнього модуля розширення",
    "HMS_1200": "Помилка периферійного обладнання",
}


def decode_hms_entry(entry: dict[str, Any] | int | str) -> str:
    """
    Decodes a single HMS error entry into a formatted string with description.
    Supports raw integer masks, 16-hex string codes (e.g. HMS0002000212FF2000), dash codes (e.g. 0300-0100), or dicts.
    Uses multi-pattern candidate matching with category translation (0002 -> 0200, 0003 -> 0300).
    """
    import re

    raw_display = ""
    hex16 = ""

    if isinstance(entry, dict):
        raw_code = entry.get("code")
        raw_attr = entry.get("attr")
        if isinstance(raw_code, int) and isinstance(raw_attr, int):
            code_hex = f"{raw_code:08X}"
            attr_hex = f"{raw_attr:08X}"
            hex16 = code_hex + attr_hex
            raw_display = f"HMS_{code_hex[:4]}_{code_hex[4:]}_{attr_hex[:4]}_{attr_hex[4:]}"
        else:
            raw_display = str(entry.get("code") or entry)
    elif isinstance(entry, int):
        code_hex = f"{entry:08X}"
        hex16 = f"{code_hex}00010001"
        raw_display = f"HMS_{code_hex[:4]}_{code_hex[4:]}_0001_0001"
    else:
        raw_display = str(entry).strip()

    if not hex16:
        clean_hex = re.sub(r"[^0-9A-Fa-f]", "", raw_display)
        if len(clean_hex) == 16:
            hex16 = clean_hex.upper()

    candidates: list[str] = []

    if len(hex16) == 16:
        c1, c2, c3, c4 = hex16[0:4], hex16[4:8], hex16[8:12], hex16[12:16]

        cat_map = {
            "0001": "0100", "0002": "0200", "0003": "0300",
            "0005": "0500", "0007": "0700", "0012": "1200",
        }
        sub_map = {
            "0001": "0100", "0002": "0200", "0003": "0300", "0004": "0400",
            "0005": "0500", "0006": "0600", "0007": "0700", "0008": "0800",
            "0009": "0900", "000A": "0A00", "000B": "0B00", "000C": "0C00",
            "000D": "0D00",
        }

        m_c1 = cat_map.get(c1, c1)
        m_c2 = sub_map.get(c2, c2)

        candidates.extend([
            f"HMS_{c1}_{c2}_{c3}_{c4}",
            f"HMS_{m_c1}_{m_c2}_{c3}_{c4}",
            f"HMS_{c1}_{c2}",
            f"HMS_{m_c1}_{m_c2}",
            f"HMS_{m_c1}_{c2}",
            f"HMS_{c1}_{m_c2}",
            f"HMS_{c1}",
            f"HMS_{m_c1}",
        ])

    norm = raw_display.replace("-", "_").upper()
    if not norm.startswith("HMS_") and not norm.startswith("HMS"):
        norm = f"HMS_{norm}"
    elif norm.startswith("HMS") and not norm.startswith("HMS_"):
        norm = f"HMS_{norm[3:]}"

    candidates.append(norm)
    parts = norm.split("_")
    if len(parts) >= 3:
        candidates.append(f"{parts[0]}_{parts[1]}_{parts[2]}")
    if len(parts) >= 2:
        candidates.append(f"{parts[0]}_{parts[1]}")

    desc: str | None = None
    for cand in candidates:
        if cand in HMS_CODE_MAP:
            desc = HMS_CODE_MAP[cand]
            break

    if desc:
        disp = norm if (raw_display and not raw_display.startswith("HMS")) else raw_display
        return f"{disp}: {desc}"
    return raw_display


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
