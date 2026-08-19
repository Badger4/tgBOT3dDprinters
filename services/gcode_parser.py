"""
3MF and Gcode metadata parser for Bambu Lab & OrcaSlicer print files.
Deep multi-source metadata parser with XML, JSON, G-code comments, filament preset suffix checks, and filename fallbacks.
"""

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

from config import logger

# Bambu Lab & OrcaSlicer internal model ID mapping
BAMBU_MODEL_MAP = {
    "n1": "Bambu Lab A1",
    "n2s": "Bambu Lab A1 mini",
    "n2": "Bambu Lab A1 mini",
    "c11": "Bambu Lab P1P",
    "c12": "Bambu Lab P1S",
    "c10": "Bambu Lab X1 Carbon",
    "x1": "Bambu Lab X1 Carbon",
    "x1c": "Bambu Lab X1 Carbon",
    "x1e": "Bambu Lab X1 Enterprise",
}


def parse_time_str(time_str: str) -> int:
    """Parses time strings like '8d 18h 54m 54s', '1h 10m 15s', '70m', '01:10:00' into total minutes."""
    if not time_str:
        return 0
    t_clean = time_str.strip().lower()

    if "total estimated time:" in t_clean:
        t_clean = t_clean.split("total estimated time:")[-1]
    elif "total estimated time =" in t_clean:
        t_clean = t_clean.split("total estimated time =")[-1]

    d_match = re.search(r"\b(\d+)\s*d\b", t_clean)
    h_match = re.search(r"\b(\d+)\s*h\b", t_clean)
    m_match = re.search(r"\b(\d+)\s*m\b", t_clean)
    s_match = re.search(r"\b(\d+)\s*s\b", t_clean)

    if d_match or h_match or m_match or s_match:
        days = int(d_match.group(1)) if d_match else 0
        hours = int(h_match.group(1)) if h_match else 0
        mins = int(m_match.group(1)) if m_match else 0
        return days * 1440 + hours * 60 + mins

    # Format: 01:10:00 or 70:00
    parts = t_clean.split(":")
    if len(parts) == 3:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    elif len(parts) == 2:
        try:
            return int(parts[0])
        except ValueError:
            pass

    return 0


def format_print_time_human(mins: int) -> str:
    """Formats minutes into human-readable format like '8д 19г 1хв (12661 хв)' or '2г 15хв (135 хв)'."""
    if mins <= 0:
        return "0 хв"
    days = mins // 1440
    rem_mins = mins % 1440
    hours = rem_mins // 60
    m = rem_mins % 60

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}г")
    if m > 0 or not parts:
        parts.append(f"{m}хв")

    time_str = " ".join(parts)
    if days > 0 or hours > 0:
        return f"~{time_str} ({mins} хв)"
    return f"~{mins} хв"


def resolve_model_name(raw_model: str) -> str:
    """
    Resolves raw model strings, filament preset names, or IDs into canonical printer names.
    Bambu Studio / OrcaSlicer tags:
      - @BBL A1M, A1M, n2s, n2 -> Bambu Lab A1 mini
      - @BBL A1, n1 -> Bambu Lab A1
      - @BBL X1C, x1c, c12, c11, p1s, p1p -> Bambu Lab P1S
    """
    if not raw_model or raw_model.strip().lower() in ["unknown", "generic"]:
        return "Unknown"

    clean = raw_model.strip()
    clean_lower = clean.lower()

    # OrcaSlicer / Bambu Studio filament preset suffix tag matching
    if "@bbl a1m" in clean_lower or "a1m" in clean_lower or "n2s" in clean_lower or "a1 mini" in clean_lower:
        return "Bambu Lab A1 mini"
    elif "@bbl a1" in clean_lower or "n1" in clean_lower:
        return "Bambu Lab A1"
    elif (
        "@bbl x1c" in clean_lower
        or "x1c" in clean_lower
        or "c12" in clean_lower
        or "c11" in clean_lower
        or "p1s" in clean_lower
        or "p1p" in clean_lower
    ):
        return "Bambu Lab P1S"

    # Direct map lookup
    if clean_lower in BAMBU_MODEL_MAP:
        return BAMBU_MODEL_MAP[clean_lower]

    return clean


def parse_3mf_file(file_bytes: bytes, filename: str = "") -> dict[str, Any]:
    """
    Parses a .3mf file bytes to extract Bambu Studio / OrcaSlicer slice metadata.
    Returns dict with keys: printer_model, filament_type, weight_g, time_mins, filename, plate_name.
    """
    result = {
        "filename": filename,
        "printer_model": "Unknown",
        "filament_type": "PLA",
        "weight_g": 0.0,
        "time_mins": 0,
        "plate_name": "plate_1.gcode",
        "valid": False,
        "error": "",
    }

    if not filename.lower().endswith(".3mf"):
        result["error"] = "Дозволено завантажувати тільки файли .3mf від Bambu Studio або OrcaSlicer."
        return result

    try:
        if zipfile.is_zipfile(io.BytesIO(file_bytes)):
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                namelist = zf.namelist()

                # 1. Search XML config files (Metadata/slice_info.config, etc)
                xml_files = [f for f in namelist if f.endswith(".config") or f.endswith(".xml") or f.endswith(".info")]
                for xf in xml_files:
                    try:
                        content_str = zf.read(xf).decode("utf-8", errors="ignore")
                        root = ET.fromstring(content_str)

                        # Extract printer model or filament preset tag
                        for elem in root.iter():
                            if elem.tag in [
                                "printer_model_id",
                                "printer_settings_id",
                                "printer_name",
                                "printer_preset",
                                "printer",
                                "filament_settings_id",
                                "filament_name",
                            ]:
                                if elem.text and elem.text.strip():
                                    res_m = resolve_model_name(elem.text)
                                    if res_m != "Unknown":
                                        result["printer_model"] = res_m
                                        break

                        # Extract filament type & weight
                        for fil in root.iter():
                            if fil.tag in ["type", "filament_type"] and fil.text and fil.text.strip():
                                result["filament_type"] = fil.text.strip()
                            elif fil.tag in ["used_g", "filament_used_g"] and fil.text and fil.text.strip():
                                try:
                                    w = float(fil.text.strip())
                                    if w > 0:
                                        result["weight_g"] = w
                                except ValueError:
                                    pass
                    except Exception:
                        pass

                # 2. Search JSON config files (Metadata/project_settings.config, etc)
                json_files = [f for f in namelist if f.endswith(".json") or f.endswith(".config")]
                for jf in json_files:
                    try:
                        content_str = zf.read(jf).decode("utf-8", errors="ignore")
                        p_json = json.loads(content_str)
                        if isinstance(p_json, dict):
                            for k in [
                                "printer_model_id",
                                "printer_settings_id",
                                "printer_name",
                                "printer",
                                "filament_settings_id",
                                "filament_name",
                            ]:
                                if k in p_json and result["printer_model"] == "Unknown":
                                    val = str(p_json[k])
                                    res_m = resolve_model_name(val)
                                    if res_m != "Unknown":
                                        result["printer_model"] = res_m
                                        break
                            if (
                                "filament_type" in p_json
                                and isinstance(p_json["filament_type"], list)
                                and p_json["filament_type"]
                            ):
                                result["filament_type"] = str(p_json["filament_type"][0])
                    except Exception:
                        pass

                # 3. Deep Scan embedded .gcode files (OrcaSlicer & Bambu Studio)
                gcode_files = [f for f in namelist if f.endswith(".gcode")]
                for gf in gcode_files:
                    try:
                        gcode_text = zf.read(gf).decode("utf-8", errors="ignore")

                        # Printer model or filament preset tag regex
                        if result["printer_model"] == "Unknown":
                            m_match = re.search(
                                r";\s*(?:printer_model_id|printer_model|printer_settings_id|printer_preset|printer|model|machine_type|filament_name|filament_preset|filament_settings_id)\s*=\s*\"?([^\";\r\n]+)\"?",
                                gcode_text,
                                re.IGNORECASE,
                            )
                            if m_match:
                                res_m = resolve_model_name(m_match.group(1))
                                if res_m != "Unknown":
                                    result["printer_model"] = res_m

                        # Filament type regex
                        f_match = re.search(
                            r";\s*(?:filament_type|filament_name)\s*=\s*\"?([^\";\r\n]+)\"?", gcode_text, re.IGNORECASE
                        )
                        if f_match:
                            f_val = f_match.group(1).strip()
                            if "ABS" in f_val.upper():
                                result["filament_type"] = "ABS"
                            elif "PETG" in f_val.upper():
                                result["filament_type"] = "PETG"
                            elif "PLA" in f_val.upper():
                                result["filament_type"] = "PLA"
                            elif "TPU" in f_val.upper():
                                result["filament_type"] = "TPU"

                        # Weight regex (supports both '=' and ':', and both '.' and ',' decimals)
                        if result["weight_g"] == 0.0:
                            w_match = re.search(
                                r";\s*(?:filament_used_g|filament used \[g\]|total filament used \[g\]|total filament weight \[g\]|filament_weight|used_g|filament_used|filament used)\s*[:=]\s*([\d\.,]+)",
                                gcode_text,
                                re.IGNORECASE,
                            )
                            if w_match:
                                try:
                                    val_w = float(w_match.group(1).replace(",", "."))
                                    if 0.0 < val_w < 5000.0:
                                        result["weight_g"] = val_w
                                except ValueError:
                                    pass

                        # Time regex (seconds)
                        if result["time_mins"] == 0:
                            t_sec_match = re.search(
                                r";\s*(?:estimated_printing_time_s|total_printing_time_s|printing_time_s)\s*=\s*(\d+)",
                                gcode_text,
                                re.IGNORECASE,
                            )
                            if t_sec_match:
                                result["time_mins"] = int(t_sec_match.group(1)) // 60
                            else:
                                t_str_match = re.search(
                                    r";\s*(?:model printing time|estimated printing time|total estimated time|printing time|print time)\s*[:=]\s*([^\r\n]+)",
                                    gcode_text,
                                    re.IGNORECASE,
                                )
                                if t_str_match:
                                    result["time_mins"] = parse_time_str(t_str_match.group(1))
                    except Exception as e:
                        logger.warning(f"Error parsing embedded gcode {gf}: {e}")

        # Fallback 4: Filename parsing for Weight, Printer Model & Time
        fname_lower = filename.lower()
        if result["weight_g"] == 0.0 and filename:
            w_fn = re.search(r"(?:_|\b)(\d+(?:[\.,]\d+)?)\s*(?:g|г|gram|grams)\b", filename, re.IGNORECASE)
            if w_fn:
                try:
                    val_fn = float(w_fn.group(1).replace(",", "."))
                    if 0.0 < val_fn < 5000.0:
                        result["weight_g"] = val_fn
                except ValueError:
                    pass

        if result["printer_model"] == "Unknown":
            res_m = resolve_model_name(filename)
            if res_m != "Unknown":
                result["printer_model"] = res_m

        if result["time_mins"] == 0:
            result["time_mins"] = parse_time_str(filename)

        # Fallback 5: Check plastic type from filename
        if "abs" in fname_lower:
            result["filament_type"] = "ABS"
        elif "petg" in fname_lower:
            result["filament_type"] = "PETG"

        result["valid"] = True

    except Exception as e:
        result["error"] = f"Помилка обробки файлу: {e}"

    return result


def check_compatibility(sliced_model: str, filament_type: str, target_printer_name: str) -> dict[str, Any]:
    """
    Checks G-code / model compatibility between sliced model and target printer.
    Tag rules:
      - P1S family: 'x1c', '@bbl x1c', 'c12', 'p1s'
      - A1 family: '@bbl a1', 'n1', 'a1'
      - A1 mini family: '@bbl a1m', 'a1m', 'n2s', 'a1 mini'
    """
    sliced_clean = sliced_model.strip()
    target_clean = target_printer_name.strip()

    def get_model_family(name_str: str) -> str:
        s = re.sub(r"[\-_]", " ", name_str.lower())
        # Check A1 mini FIRST before A1
        if "a1m" in s or "a1 mini" in s or "a1mini" in s or "n2s" in s or "n2" in s or "@bbl a1m" in s:
            return "a1_mini"
        elif "a1" in s or "n1" in s or "@bbl a1" in s:
            return "a1"
        elif (
            "x1c" in s
            or "p1s" in s
            or "c12" in s
            or "p1p" in s
            or "c11" in s
            or "x1" in s
            or "c10" in s
            or "@bbl x1c" in s
        ):
            return "p1s"
        return "unknown"

    sliced_family = get_model_family(sliced_clean)
    target_family = get_model_family(target_clean)

    if sliced_family != "unknown" and target_family != "unknown":
        if sliced_family == target_family:
            return {
                "compatible": True,
                "level": "OK",
                "reason": "✅ Ідеальна сумісність... Але тільки не думай, що це твоя заслуга, Бака! 😤💅",
            }
        else:
            return {
                "compatible": False,
                "level": "BLOCK",
                "reason": (
                    f"🛑 <b>Х-ХМПФ! НЕСУМІСНІСТЬ МОДЕЛІ ПРИНТЕРА!</b>\n"
                    f"Ти куди дивився, Бака?! Файл нарізано для <code>{sliced_clean}</code> ({sliced_family.upper()}), "
                    f"а ти хочеш запустити на <code>{target_clean}</code> ({target_family.upper()})!\n"
                    f"Стартовий G-code та макроси відрізняються! Не змушуй мене ремонтувати принтер після тебе! 😤💥"
                ),
            }

    return {
        "compatible": True,
        "level": "OK",
        "reason": "✅ Сумісність підтверджено... Тільки не кажи, що я не попереджала, Бака! 😤💅",
    }
