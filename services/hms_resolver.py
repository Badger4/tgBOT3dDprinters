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
    "HMS_0300_0800_0001_0002": "Нитка застрягла у хотенді / екструдері",
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
    "HMS_0300_0D00_0001_0003": "Закінчився філамент (екструдер порожній)",
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

    # --- Category 0700: Micro Lidar & Optical Calibration / AMS Slots ---
    "HMS_0700_8001": "Закінчився філамент в AMS (Слот 1)",
    "HMS_0700_8002": "Закінчився філамент в AMS (Слот 2)",
    "HMS_0700_8003": "Закінчився філамент в AMS (Слот 3)",
    "HMS_0700_8004": "Закінчився філамент в AMS (Слот 4)",
    "HMS_0700_8011": "Закінчився філамент в AMS",
    "HMS_0700_2000_0002_0004": "Будь ласка, витягніть філамент з екструдера",
    "HMS_0700_2000_0002_0002": "Філамент AMS відсутній або не подається в екструдер",
    "HMS_0700_2000_0002_0001": "Закінчився філамент в AMS",
    "HMS_0700_2000_0002_0003": "Збій подачі філаменту AMS",
    "HMS_0700_2000": "Закінчився або застряг філамент в AMS",
    "HMS_0700_C003": "Витягніть філамент з екструдера",
    "HMS_0700_0100_0001_0001": "Забруднено лінзу камери Micro Lidar",
    "HMS_0700_0100": "Помилка оптики Micro Lidar (Протріть серветкою)",
    "HMS_0700_0200_0001_0001": "Збій лазерного калібрування потоку (Flow Calibration)",
    "HMS_0700_0200": "Помилка оптичного калібрування потоку Micro Lidar",
    "HMS_0700": "Помилка сенсора Micro Lidar або подачі філаменту",

    # --- Category 07FF / 07FE: External Spool Holder & Virtual Slot ---
    "HMS_07FF_2000_0002_0004": "Будь ласка, витягніть зовнішній філамент з екструдера",
    "HMS_07FF_2000_0002_0002": "Зовнішній філамент відсутній або не подається в екструдер",
    "HMS_07FF_2000_0002_0001": "Закінчився зовнішній філамент",
    "HMS_07FF_2000_0002_0003": "Збій подачі / завантаження зовнішнього філаменту",
    "HMS_07FF_7000_0002_0003": "Закінчився філамент або припинилась екструзія",
    "HMS_07FF_2000": "Закінчився філамент або потрібна дія (зовнішня котушка)",
    "HMS_07FF_C003": "Витягніть філамент із зовнішньої котушки / екструдера",
    "HMS_07FF": "Помилка зовнішньої котушки або датчика подачі",
    "HMS_07FE_2000_0002_0004": "Будь ласка, витягніть зовнішній філамент з екструдера",
    "HMS_07FE_2000_0002_0002": "Зовнішній філамент відсутній або не подається в екструдер",
    "HMS_07FE_2000": "Закінчився філамент (зовнішня котушка)",
    "HMS_07FE": "Помилка зовнішньої котушки філаменту",

    # --- Category 0500: Print Job, MicroSD & System Tasks ---
    "HMS_0500_C010": "Помилка читання MicroSD карти (перевірте або замініть карту)",
    "HMS_0500_C011": "Невідомий статус завдання друку (можна ігнорувати)",
    "HMS_0500_4003": "Помилка розбору файлу друку (надішліть заново)",

    # --- Category 1200: Expansion Modules & External Accessories ---
    "HMS_1200_0100_0001_0001": "Помилка зовнішнього модуля розширення",
    "HMS_1200": "Помилка периферійного обладнання",
}


# Direct mapping for Bambu print_error and mc_print_error_code
PRINT_ERROR_MAP: dict[int | str, str] = {
    134201347: "Витягніть філамент із зовнішньої котушки / екструдера",
    0x07FFC003: "Витягніть філамент із зовнішньої котушки / екструдера",
    "07FFC003": "Витягніть філамент із зовнішньої котушки / екструдера",
    "07FF-C003": "Витягніть філамент із зовнішньої котушки / екструдера",
    0x0700C003: "Витягніть філамент із екструдера",
    "0700C003": "Витягніть філамент із екструдера",
    0x0500C010: "Помилка читання MicroSD карти (перевірте або замініть карту)",
    "0500C010": "Помилка читання MicroSD карти (перевірте або замініть карту)",
    0x0500C011: "Невідомий статус друку (можна ігнорувати)",
    "0500C011": "Невідомий статус друку (можна ігнорувати)",
    0x05004003: "Помилка розбору файлу друку (надішліть заново)",
    "05004003": "Помилка розбору файлу друку (надішліть заново)",
    83935249: "Невідомий статус друку (можна ігнорувати)",
    83935248: "Помилка читання MicroSD карти",
}


def decode_print_error(error_code: Any) -> str | None:
    """
    Decodes Bambu print_error or mc_print_error_code into a human-readable Ukrainian description.
    Returns None if error_code represents no error (0, None, empty) or is unknown.
    """
    if error_code is None:
        return None
    s = str(error_code).strip()
    if not s or s in ("0", "None", "null", "undefined"):
        return None

    if s in PRINT_ERROR_MAP:
        return PRINT_ERROR_MAP[s]

    val_int: int | None = None
    try:
        val_int = int(s, 0) if (s.startswith("0x") or s.startswith("0X")) else int(s)
    except (ValueError, TypeError):
        pass

    if val_int is not None:
        if val_int == 0:
            return None
        if val_int in PRINT_ERROR_MAP:
            return PRINT_ERROR_MAP[val_int]

        hex8 = f"{val_int:08X}"
        if hex8 in PRINT_ERROR_MAP:
            return PRINT_ERROR_MAP[hex8]

        cand1 = f"HMS_{hex8[:4]}_{hex8[4:]}"
        if cand1 in HMS_CODE_MAP:
            return HMS_CODE_MAP[cand1]

        cand2 = f"HMS_{hex8[:4]}"
        if cand2 in HMS_CODE_MAP:
            return HMS_CODE_MAP[cand2]

    return None


def decode_hms_entry(entry: dict[str, Any] | int | str) -> str:
    """
    Decodes a single HMS error entry into a formatted string with description.
    Supports raw integer masks, 16-hex string codes (e.g. 07FF-2000-0002-0004), dash codes, or dicts {"attr": ..., "code": ...}.
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

            # Bambu Lab MQTT protocol standard:
            # attr = HIGH 32 bits (subsystem / module category, e.g. 0x07FF2000)
            # code = LOW 32 bits (error index / sub-code, e.g. 0x00020004)
            # Official Bambu Wiki: HMS_07FF-2000-0002-0004
            known_prefixes = ("01", "02", "03", "05", "07", "12")
            if code_hex[:2] in known_prefixes and attr_hex[:2] not in known_prefixes:
                # Handle legacy tests or callers that passed code and attr in reverse
                hex16 = code_hex + attr_hex
                raw_display = f"HMS_{code_hex[:4]}-{code_hex[4:]}-{attr_hex[:4]}-{attr_hex[4:]}"
            else:
                hex16 = attr_hex + code_hex
                raw_display = f"HMS_{attr_hex[:4]}-{attr_hex[4:]}-{code_hex[:4]}-{code_hex[4:]}"
        else:
            raw_display = str(entry.get("code") or entry.get("attr") or entry)
    elif isinstance(entry, int):
        code_hex = f"{entry:08X}"
        hex16 = f"{code_hex}00010001"
        raw_display = f"HMS_{code_hex[:4]}-{code_hex[4:]}-0001-0001"
    else:
        raw_display = str(entry).strip()

    if not hex16:
        clean_hex = re.sub(r"[^0-9A-Fa-f]", "", raw_display)
        if len(clean_hex) == 16:
            hex16 = clean_hex.upper()

    candidates: list[str] = []

    if len(hex16) == 16:
        c1, c2, c3, c4 = hex16[0:4], hex16[4:8], hex16[8:12], hex16[12:16]

        candidates.extend([
            f"HMS_{c1}_{c2}_{c3}_{c4}",
            f"HMS_{c1}_{c2}_{c3}",
            f"HMS_{c1}_{c2}",
            f"HMS_{c1}",
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
        disp = raw_display if raw_display.startswith("HMS") else f"HMS_{raw_display.lstrip('HMS_')}"
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
