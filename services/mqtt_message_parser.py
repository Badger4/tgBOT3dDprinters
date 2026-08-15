"""
Pure functional MQTT message payload parser for Bambu Lab 3D printers.
Parses JSON telemetry payloads into structured dictionaries without requiring live MQTT connection.
"""

import json
import re
from typing import Any

from config import logger


def parse_mqtt_payload(payload_data: Any) -> dict[str, Any] | None:
    """
    Parses a raw Bambu Lab MQTT payload bytes or str.
    Returns a dictionary of parsed telemetry fields, or None if payload is invalid/empty.
    """
    if isinstance(payload_data, bytes):
        try:
            payload_str = payload_data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    elif isinstance(payload_data, str):
        payload_str = payload_data
    else:
        return None

    try:
        payload = json.loads(payload_str)
    except Exception as e:
        logger.warning(f"Failed to parse MQTT JSON payload: {e}")
        return None

    if not isinstance(payload, dict):
        return None

    print_data = payload.get("print")
    if not isinstance(print_data, dict):
        return None

    result: dict[str, Any] = {"print_data": print_data}

    if "gcode_state" in print_data and print_data["gcode_state"]:
        result["gcode_state"] = str(print_data["gcode_state"]).upper()

    if "nozzle_temper" in print_data and print_data["nozzle_temper"] is not None:
        try:
            result["nozzle_temper"] = round(float(print_data["nozzle_temper"]))
        except (ValueError, TypeError):
            pass

    if "bed_temper" in print_data and print_data["bed_temper"] is not None:
        try:
            result["bed_temper"] = round(float(print_data["bed_temper"]))
        except (ValueError, TypeError):
            pass

    if "mc_percent" in print_data and print_data["mc_percent"] is not None:
        try:
            result["mc_percent"] = max(0, min(100, int(print_data["mc_percent"])))
        except (ValueError, TypeError):
            pass

    if "mc_remaining_time" in print_data and print_data["mc_remaining_time"] is not None:
        try:
            result["mc_remaining_time"] = max(0, int(print_data["mc_remaining_time"]))
        except (ValueError, TypeError):
            pass

    if "layer_num" in print_data and print_data["layer_num"] is not None:
        try:
            result["layer_num"] = max(0, int(print_data["layer_num"]))
        except (ValueError, TypeError):
            pass

    if "total_layer_num" in print_data and print_data["total_layer_num"] is not None:
        try:
            result["total_layer_num"] = max(0, int(print_data["total_layer_num"]))
        except (ValueError, TypeError):
            pass

    if "subtask_name" in print_data and print_data["subtask_name"] is not None:
        result["subtask_name"] = str(print_data["subtask_name"])

    if "spd_lvl" in print_data and print_data["spd_lvl"] is not None:
        try:
            result["spd_lvl"] = int(print_data["spd_lvl"])
        except (ValueError, TypeError):
            pass

    if "spd_mag" in print_data and print_data["spd_mag"] is not None:
        try:
            result["spd_mag"] = int(print_data["spd_mag"])
        except (ValueError, TypeError):
            pass

    if "lights_report" in print_data and isinstance(print_data["lights_report"], list):
        for light in print_data["lights_report"]:
            if isinstance(light, dict) and light.get("node") == "chamber_light":
                result["chamber_light_state"] = light.get("mode", "off")

    if "hms" in print_data and isinstance(print_data["hms"], list):
        result["hms_errors"] = print_data["hms"]

    if "ams" in print_data and isinstance(print_data["ams"], dict):
        ams_info = print_data["ams"]
        if "ams_exist_bits" in ams_info:
            result["ams_exist_bits"] = str(ams_info["ams_exist_bits"])
        if "tray_now" in ams_info:
            try:
                result["active_ams_tray"] = int(ams_info["tray_now"])
            except (ValueError, TypeError):
                result["active_ams_tray"] = 255

        if "ams" in ams_info and isinstance(ams_info["ams"], list):
            result["ams_units"] = ams_info["ams"]
            trays_dict: dict[str, dict[str, Any]] = {}
            for unit in ams_info["ams"]:
                if isinstance(unit, dict) and "tray" in unit and isinstance(unit["tray"], list):
                    for tray in unit["tray"]:
                        if isinstance(tray, dict):
                            slot_id = str(tray.get("id", ""))
                            if slot_id != "":
                                is_empty = bool(tray.get("empty", False))
                                raw_color = str(tray.get("tray_color") or "")
                                hex_color = f"#{raw_color[:6]}" if len(raw_color) >= 6 else ""
                                trays_dict[slot_id] = {
                                    "id": slot_id,
                                    "empty": is_empty,
                                    "type": str(tray.get("tray_type") or ""),
                                    "sub_brands": str(tray.get("tray_sub_brands") or ""),
                                    "color": hex_color,
                                    "remain": int(tray.get("remain", -1)),
                                }
            if trays_dict:
                result["ams_trays_info"] = trays_dict

            if ams_info["ams"]:
                unit = ams_info["ams"][0]
                if isinstance(unit, dict):
                    if "humidity" in unit:
                        try:
                            result["ams_humidity_idx"] = int(unit["humidity"])
                        except (ValueError, TypeError):
                            pass
                    if "temp" in unit:
                        try:
                            result["ams_temp"] = float(unit["temp"])
                        except (ValueError, TypeError):
                            pass

    if "vt_tray" in print_data and isinstance(print_data["vt_tray"], dict):
        vt = print_data["vt_tray"]
        vt_empty = bool(vt.get("empty", False))
        vt_color = str(vt.get("tray_color") or "")
        vt_hex = f"#{vt_color[:6]}" if len(vt_color) >= 6 else ""
        result["vt_tray_info"] = {
            "id": "255",
            "empty": vt_empty,
            "type": str(vt.get("tray_type") or ""),
            "sub_brands": str(vt.get("tray_sub_brands") or ""),
            "color": vt_hex,
            "remain": int(vt.get("remain", -1)),
        }

    return result


def extract_subtask_weight(subtask_name: str) -> float:
    """Extracts filament weight in grams from subtask filename regex."""
    if not subtask_name:
        return 0.0
    m = re.search(r"(?:_|\b)(\d+(?:[\.,]\d+)?)\s*(?:g|г|gram|grams)\b", subtask_name, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1).replace(",", "."))
            if 0 < val < 5000:
                return val
        except ValueError:
            pass
    return 0.0
