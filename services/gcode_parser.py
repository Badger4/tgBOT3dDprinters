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


def sanitize_object_name(name: str) -> str:
    """Sanitizes object names, making parsing 100% idempotent and preventing spatial word multiplication."""
    if not name or not isinstance(name, str):
        return ""
    clean = str(name).strip()

    # Extract hashtag index if present (#1, #2)
    m_num = re.search(r"#(\d+)", clean)
    num_str = f" #{m_num.group(1)}" if m_num else ""

    # Extract unique spatial keywords once from clean string
    clean_lower = clean.lower()
    y_word = ""
    if "ззаду" in clean_lower:
        y_word = "Ззаду"
    elif "спереду" in clean_lower:
        y_word = "Спереду"

    x_word = ""
    if "ліворуч" in clean_lower:
        x_word = "Ліворуч"
    elif "праворуч" in clean_lower:
        x_word = "Праворуч"

    center_word = ""
    if not y_word and not x_word and ("по центру" in clean_lower or "центр" in clean_lower):
        center_word = "По центру"

    spatial_parts = [w for w in [y_word, x_word, center_word] if w]
    spatial_str = " ".join(spatial_parts)
    pos_tag = f" ({spatial_str})" if spatial_str else ""

    # Strip ALL #N and ALL (...) from base name completely
    base = re.sub(r"\s*#\d+.*", "", clean)
    base = re.sub(r"\s*\(.*?\)", "", base).strip()
    if not base:
        base = "Об'єкт"

    return f"{base}{num_str}{pos_tag}".strip()


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
    objects_list: list[dict[str, str]] = []
    bbox_list: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "filename": filename,
        "printer_model": "Unknown",
        "filament_type": "PLA",
        "weight_g": 0.0,
        "time_mins": 0,
        "plate_name": "plate_1.gcode",
        "objects": objects_list,
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

                # 1. Primary Object Extraction: Metadata/slice_info.config
                if "Metadata/slice_info.config" in namelist:
                    try:
                        content_str = zf.read("Metadata/slice_info.config").decode("utf-8", errors="ignore")
                        root = ET.fromstring(content_str)
                        for elem in root.iter():
                            tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if tag_name == "object":
                                obj_id = elem.get("identify_id") or elem.get("id") or elem.get("identify") or elem.get("object_id")
                                obj_name = elem.get("name") or elem.get("part_name")
                                if obj_id:
                                    obj_id_str = str(obj_id).strip()
                                    obj_name_str = str(obj_name).strip() if obj_name else f"Об'єкт {obj_id_str}"
                                    if not any(o["id"] == obj_id_str for o in objects_list):
                                        objects_list.append({"id": obj_id_str, "name": obj_name_str})
                    except Exception:
                        pass

                # 1b. Fallback XML config files if slice_info.config didn't yield objects
                if not objects_list:
                    xml_files = [f for f in namelist if f.endswith(".config") or f.endswith(".xml") or f.endswith(".info") or f.endswith(".model") or f.startswith("3D/")]
                    for xf in xml_files:
                        try:
                            content_str = zf.read(xf).decode("utf-8", errors="ignore")
                            root = ET.fromstring(content_str)
                            for elem in root.iter():
                                tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                                if tag_name in ["object", "item", "component"]:
                                    obj_id = elem.get("identify_id") or elem.get("id") or elem.get("identify") or elem.get("object_id") or elem.get("objectid")
                                    obj_name = elem.get("name") or elem.get("part_name") or elem.get("filename")
                                    obj_type = elem.get("type", "").lower()
                                    if obj_type == "other":
                                        continue
                                    if obj_id:
                                        obj_id_str = str(obj_id).strip()
                                        obj_name_str = str(obj_name).strip() if obj_name else f"Об'єкт {obj_id_str}"
                                        if not any(o["id"] == obj_id_str for o in objects_list):
                                            objects_list.append({"id": obj_id_str, "name": obj_name_str})
                        except Exception:
                            pass

                # 2. Search XML files for metadata & printer presets
                xml_files = [f for f in namelist if f.endswith(".config") or f.endswith(".xml") or f.endswith(".info") or f.endswith(".model") or f.startswith("3D/")]
                for xf in xml_files:
                    try:
                        content_str = zf.read(xf).decode("utf-8", errors="ignore")
                        root = ET.fromstring(content_str)

                        # Extract printer model or filament preset tag
                        for elem in root.iter():
                            tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if tag_name in [
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
                        for elem in root.iter():
                            tag_name = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                            if tag_name in ["type", "filament_type"] and elem.text and elem.text.strip():
                                result["filament_type"] = elem.text.strip()
                            elif tag_name in ["used_g", "filament_used_g"] and elem.text and elem.text.strip():
                                try:
                                    w = float(elem.text.strip())
                                    if w > 0:
                                        result["weight_g"] = w
                                except ValueError:
                                    pass
                    except Exception:
                        pass

                # 3. Search JSON config files for bbox_objects fallback & preset metadata
                json_files = [f for f in namelist if f.endswith(".json") or f.endswith(".config")]
                for jf in json_files:
                    try:
                        content_str = zf.read(jf).decode("utf-8", errors="ignore")
                        p_json = json.loads(content_str)
                        if isinstance(p_json, dict):
                            if "bbox_objects" in p_json and isinstance(p_json["bbox_objects"], list):
                                if not bbox_list:
                                    bbox_list = p_json["bbox_objects"]
                                for b_obj in p_json["bbox_objects"]:
                                    if isinstance(b_obj, dict) and "id" in b_obj:
                                        b_id = str(b_obj["id"]).strip()
                                        b_name = str(b_obj.get("name") or f"Об'єкт {b_id}").strip()
                                        b_box = b_obj.get("bbox")
                                        matching = [o for o in objects_list if o["id"] == b_id]
                                        if matching:
                                            if b_box and isinstance(b_box, list):
                                                matching[0]["bbox"] = b_box
                                        else:
                                            obj_dict: dict[str, Any] = {"id": b_id, "name": b_name}
                                            if b_box and isinstance(b_box, list):
                                                obj_dict["bbox"] = b_box
                                            objects_list.append(obj_dict)

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

                        # Object IDs regex from Gcode comments (e.g. ; PRINT_OBJECT_START name='Part' id=206)
                        for obj_match in re.finditer(
                            r";\s*(?:PRINT_OBJECT_START|object_info|object)\b.*?(?:id[:=]\s*(\d+)|name[:=]\s*['\"]?([^'\";\r\n]+)['\"]?)",
                            gcode_text,
                            re.IGNORECASE,
                        ):
                            g_id = obj_match.group(1)
                            g_name = obj_match.group(2) or (f"Об'єкт {g_id}" if g_id else None)
                            if g_id:
                                g_id_str = str(g_id).strip()
                                if not any(o["id"] == g_id_str for o in objects_list):
                                    objects_list.append({"id": g_id_str, "name": str(g_name).strip() if g_name else f"Об'єкт {g_id_str}"})

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

        # Spatial position calculator relative to 3D print bed coordinates (X: Left/Right, Y: Front/Back)
        def get_spatial_label(bbox: list[float], bed_size_x: float = 256.0, bed_size_y: float = 256.0) -> str:
            if len(bbox) < 4:
                return ""
            try:
                xmin, ymin, xmax, ymax = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
                cx = (xmin + xmax) / 2.0
                cy = (ymin + ymax) / 2.0

                # Y-axis position (0 = Front, max = Back)
                if cy > bed_size_y * 0.65:
                    y_lbl = "Ззаду"
                elif cy < bed_size_y * 0.35:
                    y_lbl = "Спереду"
                else:
                    y_lbl = "Центр"

                # X-axis position (0 = Left, max = Right)
                if cx > bed_size_x * 0.65:
                    x_lbl = "Праворуч"
                elif cx < bed_size_x * 0.35:
                    x_lbl = "Ліворуч"
                else:
                    x_lbl = "Центр"

                if y_lbl == "Центр" and x_lbl == "Центр":
                    return "По центру"
                elif y_lbl == "Центр":
                    return x_lbl
                elif x_lbl == "Центр":
                    return y_lbl
                else:
                    return f"{y_lbl} {x_lbl}"
            except Exception:
                return ""

        # Clean any pre-existing tags & disambiguate duplicate object names cleanly (e.g. "Куб #1 (Ззаду Праворуч)")
        for obj in objects_list:
            raw_n = obj.get("name", "")
            # Strip any previous #N or (...) spatial tags to prevent repetitive string stacking
            clean_n = re.sub(r"\s*#\d+.*$", "", raw_n)
            clean_n = re.sub(r"\s*\(.*?\)$", "", clean_n).strip()
            obj["name"] = clean_n if clean_n else raw_n

        name_counts: dict[str, int] = {}
        for obj in objects_list:
            name_counts[obj["name"]] = name_counts.get(obj["name"], 0) + 1

        name_indices: dict[str, int] = {}
        for i, obj in enumerate(objects_list):
            base_name = obj["name"]
            pos_str = ""
            if i < len(bbox_list) and isinstance(bbox_list[i], dict) and "bbox" in bbox_list[i]:
                if "bbox" not in obj:
                    obj["bbox"] = bbox_list[i]["bbox"]
                b_lbl = get_spatial_label(bbox_list[i]["bbox"])
                if b_lbl:
                    pos_str = f" ({b_lbl})"

            if name_counts[base_name] > 1:
                idx = name_indices.get(base_name, 1)
                name_indices[base_name] = idx + 1
                obj["name"] = f"{base_name} #{idx}{pos_str}"
            else:
                if pos_str:
                    obj["name"] = f"{base_name}{pos_str}"
                else:
                    obj["name"] = base_name

        result["objects"] = objects_list
        result["valid"] = True

    except Exception as e:
        result["error"] = f"Помилка обробки файлу: {e}"

    return result


HARDCODED_FILAMENT_TYPES = [
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


def normalize_filament_name(raw_name: str) -> str:
    """Normalizes filament preset names/types to canonical hardcoded filament types."""
    if not raw_name or not isinstance(raw_name, str) or str(raw_name).startswith("<") or str(raw_name).strip().lower() in ["unknown", "generic", "невизначено", ""]:
        return ""
    s = str(raw_name).strip().upper()
    for main_type in HARDCODED_FILAMENT_TYPES:
        pattern = r"(?<![A-Z0-9\-])" + re.escape(main_type) + r"(?![A-Z0-9\-])"
        if re.search(pattern, s, re.IGNORECASE):
            return main_type
    return s


def get_printer_active_filament(printer: Any, spools_map: dict | None = None) -> str:
    """Returns the active filament type/spool mounted on the printer's active slot."""
    active_key = str(printer.get_active_slot_key()) if (hasattr(printer, "get_active_slot_key") and callable(getattr(printer, "get_active_slot_key"))) else "255"

    # 1. Check mounted spool from Warehouse
    if spools_map and isinstance(spools_map, dict):
        for s_id, spool in spools_map.items():
            if isinstance(spool, dict) and spool.get("assigned_printer_id") == getattr(printer, "id", None):
                if str(spool.get("assigned_slot_key")) == active_key:
                    s_type = spool.get("type") or spool.get("name") or ""
                    if s_type and isinstance(s_type, str) and not s_type.startswith("<"):
                        return str(s_type)

    # 2. Check AMS trays info for active slot
    ams_trays = getattr(printer, "ams_trays_info", {})
    if isinstance(ams_trays, dict) and active_key in ams_trays:
        t_info = ams_trays[active_key]
        if isinstance(t_info, dict) and t_info.get("type"):
            brand_sub = t_info.get("sub_brands", "")
            return f"Bambu {t_info['type']} {brand_sub}".strip() if brand_sub else f"Bambu {t_info['type']}"

    # 3. Fallback to printer.filament_type attribute
    fil_type = getattr(printer, "filament_type", "Невизначено")
    if fil_type and isinstance(fil_type, str) and fil_type != "Невизначено" and not fil_type.startswith("<"):
        return str(fil_type)

    return ""


def get_bambu_model_code(name_str: str) -> str:
    """
    Hardcoded Bambu Lab printer model mapping:
      - a1 mini -> @BBL A1M
      - a1 -> @BBL A1
      - a2l -> @BBL A2L
      - p1s -> @BBL X1C
      - h2c -> @BBL H2C
      - h2d -> @BBL H2D
      - h2d pro -> @BBL H2DP
      - h2s -> @BBL H2S
      - p1p -> @BBL P1P
      - p2s -> @BBL P2S
      - x1, x1 carbon, x1e -> @BBL X1C
      - x2d -> @BBL X2D
    """
    if not name_str:
        return "UNKNOWN"
    s = re.sub(r"[\-_]", " ", str(name_str).lower()).strip()

    if "a1 mini" in s or "a1mini" in s or "a1m" in s or "@bbl a1m" in s or "n2s" in s or "n2" in s:
        return "@BBL A1M"
    if "a1" in s or "@bbl a1" in s or "n1" in s:
        return "@BBL A1"
    if "a2l" in s or "@bbl a2l" in s:
        return "@BBL A2L"
    if "h2d pro" in s or "h2dpro" in s or "h2dp" in s or "@bbl h2dp" in s:
        return "@BBL H2DP"
    if "h2c" in s or "@bbl h2c" in s:
        return "@BBL H2C"
    if "h2d" in s or "@bbl h2d" in s:
        return "@BBL H2D"
    if "h2s" in s or "@bbl h2s" in s:
        return "@BBL H2S"
    if "p1p" in s or "@bbl p1p" in s:
        return "@BBL P1P"
    if "p2s" in s or "@bbl p2s" in s:
        return "@BBL P2S"
    if "x2d" in s or "@bbl x2d" in s:
        return "@BBL X2D"
    if "p1s" in s or "x1 carbon" in s or "x1c" in s or "x1e" in s or "x1" in s or "@bbl x1c" in s or "c12" in s or "c10" in s:
        return "@BBL X1C"

    return "UNKNOWN"


def check_compatibility(
    sliced_model: str,
    filament_type: str,
    target_printer_name: str,
    target_filament: str = "",
) -> dict[str, Any]:
    """
    Checks G-code / model & filament compatibility between sliced 3MF metadata and target printer.
    Stage 1 (Hardware): Checks printer model code (@BBL A1M vs @BBL A1 vs @BBL X1C, etc).
    Stage 2 (Material): Checks filament type (e.g. TPU vs ABS).
    """
    sliced_code = get_bambu_model_code(sliced_model)
    target_code = get_bambu_model_code(target_printer_name)

    if sliced_code != "UNKNOWN" and target_code != "UNKNOWN" and sliced_code != target_code:
        return {
            "compatible": False,
            "reason_type": "PRINTER",
            "level": "BLOCK",
            "reason": "🛑 Принтер несумісний з файлом",
        }

    # Stage 2: Material Check (Filament Type)
    norm_sliced_fil = normalize_filament_name(filament_type)
    norm_target_fil = normalize_filament_name(target_filament)

    if norm_sliced_fil and norm_target_fil and norm_sliced_fil != norm_target_fil:
        return {
            "compatible": False,
            "reason_type": "FILAMENT",
            "level": "BLOCK",
            "reason": "🛑 Філамент несумісний з файлом",
        }

    return {
        "compatible": True,
        "reason_type": "OK",
        "level": "OK",
        "reason": "✅ Сумісність підтверджено!",
    }
