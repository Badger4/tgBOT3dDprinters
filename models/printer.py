"""
Bambu Lab 3D Printer MQTT client and domain model.
"""

import asyncio
import concurrent.futures
import hashlib
import html
import inspect
import io
import json
import re
import ssl
import time
import uuid
import zipfile
from typing import Any

import paho.mqtt.client as mqtt

from config import STORAGE_DIR, logger
from models.enums import AMSSlot
from models.printer_commands import PrinterCommandsMixin
from models.printer_maintenance import PrinterMaintenanceMixin
from services.ftps_client import extract_model_weight, fetch_bambu_ftps_weight, upload_3mf_to_bambu, verify_bambu_file_size
from services.gcode_parser import parse_3mf_file
from services.hms_resolver import decode_print_error, format_hms_errors
from services.mqtt_message_parser import extract_subtask_weight, parse_mqtt_payload
from storage.manager import StorageManager

_MQTT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="bambu_mqtt")

DEFAULT_MAINTENANCE_ITEMS = {
    "rails": {
        "key": "rails",
        "name": "Змащення валів & направляючих",
        "counter_hours": 0.0,
        "interval_hours": 100.0,
        "last_reset": 0.0,
    },
    "belts": {
        "key": "belts",
        "name": "Перевірка натягу ременів",
        "counter_hours": 0.0,
        "interval_hours": 150.0,
        "last_reset": 0.0,
    },
}


def build_ams_mapping(active_slot: int | str | None, has_ams: bool = True, use_ams: bool = True) -> tuple[list[int], bool]:
    """
    Constructs compliant Bambu Lab MQTT ams_mapping array: [Virtual_T0, Virtual_T1, Virtual_T2, Virtual_T3].
    Values must be 0-indexed integers representing physical slots (0 for Slot 1, 3 for Slot 4).
    Unused slots are -1.
    For single-color print using physical Slot X (1-4): [slot_idx, -1, -1, -1], use_ams=True.
    For physical Slot 4: [3, -1, -1, -1].
    For physical Slot 1: [0, -1, -1, -1].
    For print without AMS / external spool (254, 255, None or use_ams=False): [], use_ams=False.
    """
    if not has_ams or not use_ams or active_slot is None:
        return [], False

    str_slot = str(active_slot).strip().upper()
    if str_slot in ["254", "255", "VT", "EXTERNAL", "NONE", ""]:
        return [], False

    # Check for slot designations like A1-A4, Slot 1-4, Слот 1-4
    if any(k in str_slot for k in ["A1", "SLOT 1", "SLOT1", "СЛОТ 1", "СЛОТ1"]):
        slot_idx = 0
    elif any(k in str_slot for k in ["A2", "SLOT 2", "SLOT2", "СЛОТ 2", "СЛОТ2"]):
        slot_idx = 1
    elif any(k in str_slot for k in ["A3", "SLOT 3", "SLOT3", "СЛОТ 3", "СЛОТ3"]):
        slot_idx = 2
    elif any(k in str_slot for k in ["A4", "SLOT 4", "SLOT4", "СЛОТ 4", "СЛОТ4"]):
        slot_idx = 3
    else:
        import re
        m_digit = re.search(r"\b([1-4])\b", str_slot)
        if m_digit:
            slot_idx = int(m_digit.group(1)) - 1
        else:
            try:
                slot_num = int(str_slot)
                if 1 <= slot_num <= 4:
                    slot_idx = slot_num - 1
                elif slot_num == 0:
                    slot_idx = 0
                else:
                    return [], False
            except (ValueError, TypeError):
                return [], False

    if not (0 <= slot_idx <= 3):
        return [], False

    mapping = [slot_idx, -1, -1, -1]
    return mapping, True


class BambuPrinter(PrinterCommandsMixin, PrinterMaintenanceMixin):
    """Manages Bambu Lab 3D Printer telemetry and MQTT control."""

    def __init__(self, config: dict[str, Any], storage: StorageManager, save_callback: Any | None = None):
        self.id = str(config.get("id") or uuid.uuid4())
        self.name = config.get("name", "Bambu Printer")
        self.ip = config.get("ip", "")
        raw_code = config.get("accessCode") or config.get("code") or ""
        self.access_code = str(raw_code).strip() if isinstance(raw_code, (str, int, float)) else ""
        self.serial_number = str(config.get("serialNumber") or config.get("serial") or "")
        self.printer_model = str(config.get("printer_model") or config.get("model") or "A1").strip()
        self.spool_db_file = config.get("spoolDbFile", f"./spool_{self.id}.json")
        raw_fg = float(config.get("filament_grams", 1000.0))
        self._filament_grams = max(0.0, round(raw_fg, 2))
        self.notify = config.get("notify", True)
        self.log = config.get("log", True)
        self.price_per_kg = float(config.get("price_per_kg", 650.0))
        self.power_watts = float(config.get("power_watts", 120.0))
        self.electricity_rate_uah = float(config.get("electricity_rate_uah", 4.32))
        self.active_spool_id = str(config.get("active_spool_id", ""))

        # Maintenance & Print Hours Tracking
        self.total_print_hours = float(config.get("total_print_hours", 0.0))
        self.maintenance_hours_counter = float(config.get("maintenance_hours_counter", 0.0))
        self.maintenance_interval_hours = int(config.get("maintenance_interval_hours", 100))
        self.last_maintenance_timestamp = float(config.get("last_maintenance_timestamp", 0.0))

        raw_maint_items = config.get("maintenance_items") or {}
        self.maintenance_items: dict[str, dict[str, Any]] = {}
        for k, def_item in DEFAULT_MAINTENANCE_ITEMS.items():
            user_item = raw_maint_items.get(k, {})
            c_hrs = float(user_item.get("counter_hours", self.maintenance_hours_counter if k == "rails" else 0.0))
            i_hrs = float(
                user_item.get(
                    "interval_hours", self.maintenance_interval_hours if k == "rails" else def_item["interval_hours"]
                )
            )
            self.maintenance_items[k] = {
                "key": k,
                "name": def_item["name"],
                "counter_hours": c_hrs,
                "interval_hours": i_hrs,
                "last_reset": float(user_item.get("last_reset", 0.0)),
            }

        # Per-slot AMS filament weight tracking (Keys: "0"=A1, "1"=A2, "2"=A3, "3"=A4, "254"=External vt_tray)
        raw_ams_slots = config.get("ams_slots") or {}
        if "255" in raw_ams_slots and "254" not in raw_ams_slots:
            raw_ams_slots["254"] = raw_ams_slots.pop("255")
        default_slots = {
            AMSSlot.A1.value: 1000.0,
            AMSSlot.A2.value: 1000.0,
            AMSSlot.A3.value: 1000.0,
            AMSSlot.A4.value: 1000.0,
            AMSSlot.EXTERNAL.value: 1000.0,
        }
        self.ams_slots: dict[str, float] = {k: float(v) for k, v in {**default_slots, **raw_ams_slots}.items()}
        self._previous_ams_slots: dict[str, float] = dict(self.ams_slots)

        self.storage = storage
        self.save_callback = save_callback
        self._client: mqtt.Client | None = None
        self._is_printing = False
        self._was_running = False
        self._job_started_from_app = False
        self._has_active_context = False
        self._history_recorded = False
        self._current_job_grams = 0.0
        self._job_deducted = False
        self._is_calibrating = False
        self._last_completed_subtask: str | None = None
        self.last_job_grams = 0.0
        self.current_job_objects: list[dict[str, Any]] = []
        self.skipped_objects: list[int] = []
        self._skipped_at_progress: dict[int, int] = {}
        self._skip_refund_applied = False
        self._plate_gif_cache: bytes | None = None
        self._plate_diagram_cache: bytes | None = None
        self._ftps_fetching = False
        self._ftps_attempted = False
        self._main_loop: asyncio.AbstractEventLoop | None = None

        # Live telemetry
        self.gcode_state = config.get("gcode_state", "IDLE")
        self.nozzle_temper = int(config.get("nozzle_temper", 0))
        self.nozzle_target_temper = int(config.get("nozzle_target_temper", 0))
        self.bed_temper = int(config.get("bed_temper", 0))
        self.bed_target_temper = int(config.get("bed_target_temper", 0))
        self.chamber_temper = int(config.get("chamber_temper", 0))
        self.wifi_signal = str(config.get("wifi_signal", ""))
        self.gcode_start_time = int(config.get("gcode_start_time", 0))
        self.print_error = int(config.get("print_error", 0))
        self.mc_print_error_code = str(config.get("mc_print_error_code", ""))
        self.fail_reason = str(config.get("fail_reason", ""))
        self.hw_switch_state = int(config.get("hw_switch_state", 0))
        self.nozzle_diameter = str(config.get("nozzle_diameter", "0.4"))
        self.ams_status = int(config.get("ams_status", 0))
        self.tray_exist_bits = str(config.get("tray_exist_bits", ""))
        self.xcam_info: dict = config.get("xcam_info", {})
        self.upgrade_state: dict = config.get("upgrade_state", {})
        self.upload_info: dict = config.get("upload_info", {})
        self.mc_percent = int(config.get("mc_percent", 0))
        self.mc_remaining_time = int(config.get("mc_remaining_time", 0))
        self.layer_num = int(config.get("layer_num", 0))
        self.total_layer_num = int(config.get("total_layer_num", 0))
        self.subtask_name = config.get("subtask_name", "")
        self.filament_type = config.get("filament_type", "Невизначено")
        self.spd_lvl = int(config.get("spd_lvl", 2))
        self.spd_mag = int(config.get("spd_mag", 100))
        self.chamber_light_state = "off"
        self.hms_errors: list = []
        self.hms_resolved: list[str] = []
        self.finish_timestamp: float = 0.0
        self.job_start_time: float = 0.0
        self.ams_units: list = []
        self.ams_humidity_idx: int = int(config.get("ams_humidity_idx", 0))
        self.ams_humidity_raw: int = int(config.get("ams_humidity_raw", 0))
        try:
            self.ams_temp: float = float(config.get("ams_temp", 0.0) or 0.0)
        except (ValueError, TypeError):
            self.ams_temp = 0.0
        self.active_ams_tray: int = 255
        self.target_ams_tray: int | None = None
        self.last_active_slot: str | None = None
        self._current_job_slot_key: str | None = None
        self.ams_exist_bits: str = str(config.get("ams_exist_bits", ""))
        raw_ams_enabled = config.get("ams_enabled")
        if raw_ams_enabled is None or str(raw_ams_enabled).strip().lower() in ["auto", "none", ""]:
            self.ams_enabled = None
        else:
            self.ams_enabled = bool(raw_ams_enabled)
        self.ams_trays_info: dict[str, dict] = dict(config.get("ams_trays_info", {}))
        raw_has_ams = config.get("has_ams")
        self._has_ams_telemetry: bool | None = bool(raw_has_ams) if raw_has_ams is not None else None
        self._known_trays_state: dict[str, dict] = {}
        self._trays_initialized: bool = False
        self.tray_event_callback: Any | None = None
        self._pending_tray_events: list[dict] = []

    @property
    def has_ams(self) -> bool:
        """
        Automatic AMS Hardware Detection from live Bambu MQTT telemetry
        and persisted hardware state.
        """
        if self.ams_enabled is False:
            return False
        if self.ams_enabled is True:
            return True

        if self._has_ams_telemetry is False:
            return False
        if self._has_ams_telemetry is True:
            return True

        exist_bits = str(getattr(self, "ams_exist_bits", "")).strip()
        if exist_bits in ["0", "0000"]:
            return False

        # Check active tray index (0..15 indicates active AMS slot feeding)
        if self.active_ams_tray is not None and 0 <= self.active_ams_tray <= 15:
            return True

        t_bits = str(getattr(self, "tray_exist_bits", "")).strip()
        if t_bits not in ["0", "0000", ""]:
            return True

        units = getattr(self, "ams_units", [])
        if isinstance(units, list) and units:
            for unit in units:
                if isinstance(unit, dict) and unit:
                    if unit.get("humidity") is not None or unit.get("humidity_raw") is not None or unit.get("temp") is not None:
                        return True
                    trays = unit.get("tray", [])
                    if isinstance(trays, list) and len(trays) > 0:
                        for t in trays:
                            if isinstance(t, dict):
                                t_type = str(t.get("tray_type", "")).strip().lower()
                                if t_type and t_type != "empty" and not t.get("empty", False):
                                    return True

        # Check loaded trays in ams_trays_info (Slots 0..3) ONLY if ams_exist_bits is not explicitly 0
        has_physical_trays = any(
            isinstance(self.ams_trays_info.get(k), dict)
            and not self.ams_trays_info[k].get("empty", False)
            and str(self.ams_trays_info[k].get("type") or "").strip().lower() not in ["", "empty"]
            for k in ["0", "1", "2", "3"]
        )
        if has_physical_trays and exist_bits not in ["0", "0000"]:
            return True

        return False

    def get_matching_ams_slots(
        self,
        filament_type: str,
        tray_info_idx: str = "",
        color: str = "",
        filament_name: str = "",
    ) -> list[dict[str, Any]]:
        """
        Returns all AMS slots (0-3) that match the requested filament type,
        sorted by relevance score (descending).
        """
        if not filament_type or not self.has_ams:
            return []

        from services.gcode_parser import normalize_filament_name

        req_norm = normalize_filament_name(filament_type)
        req_upper = req_norm.upper() if req_norm else str(filament_type).strip().upper()
        req_tray_idx = str(tray_info_idx or "").strip().upper()
        req_color = str(color or "").strip().lstrip("#").upper()
        if len(req_color) == 6:
            req_color += "FF"

        candidates = []
        for slot_idx in range(4):
            slot_k = str(slot_idx)
            tray = self.ams_trays_info.get(slot_k)
            if not tray or tray.get("empty", False):
                continue
            tray_type = str(tray.get("type") or tray.get("tray_type") or "").strip()
            if not tray_type or tray_type.lower() == "empty":
                continue

            norm_tray = normalize_filament_name(tray_type)
            tray_upper = norm_tray.upper() if norm_tray else tray_type.upper()

            is_match = False
            score = 0

            if norm_tray and norm_tray == req_norm:
                is_match = True
                score += 100
            elif req_upper and (req_upper in tray_upper or tray_upper in req_upper):
                is_match = True
                score += 60

            if not is_match:
                continue

            slot_tray_idx = str(tray.get("tray_info_idx") or "").strip().upper()
            if req_tray_idx and slot_tray_idx:
                if req_tray_idx == slot_tray_idx:
                    score += 500
                elif req_tray_idx[:3] == slot_tray_idx[:3]:
                    score += 50

            slot_color_raw = str(tray.get("tray_color") or tray.get("color") or "").strip().lstrip("#").upper()
            if len(slot_color_raw) == 6:
                slot_color_raw += "FF"
            if req_color and slot_color_raw and len(req_color) >= 6 and len(slot_color_raw) >= 6:
                try:
                    r1, g1, b1 = int(req_color[:2], 16), int(req_color[2:4], 16), int(req_color[4:6], 16)
                    r2, g2, b2 = int(slot_color_raw[:2], 16), int(slot_color_raw[2:4], 16), int(slot_color_raw[4:6], 16)
                    dist = ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5
                    if dist < 20:
                        score += 300
                    elif dist < 80:
                        score += 150
                    else:
                        score += max(0, int(100 - dist / 4))
                except Exception:
                    pass

            slot_sub = str(tray.get("sub_brands") or tray.get("tray_id_name") or "").strip().upper()
            req_name_up = str(filament_name or "").strip().upper()
            if req_name_up and slot_sub and (slot_sub in req_name_up or req_name_up in slot_sub):
                score += 100

            candidates.append({
                "slot_idx": slot_idx,
                "slot_num": slot_idx + 1,
                "type": tray_type,
                "tray_info_idx": slot_tray_idx,
                "sub_brands": tray.get("sub_brands", ""),
                "color": tray.get("color", ""),
                "score": score,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def find_matching_ams_slot(
        self,
        filament_type: str,
        tray_info_idx: str = "",
        color: str = "",
        filament_name: str = "",
    ) -> int | None:
        """
        Looks up which physical AMS slot (0-3) best matches the requested filament.
        Returns 0-indexed slot number (0 for Slot 1, 3 for Slot 4), or None if not found.
        """
        matches = self.get_matching_ams_slots(
            filament_type=filament_type,
            tray_info_idx=tray_info_idx,
            color=color,
            filament_name=filament_name,
        )
        if matches:
            return matches[0]["slot_idx"]
        return None

    def get_loaded_ams_summary(self) -> str:
        """Returns human-readable summary of loaded AMS slots (Slots 1-4)."""
        parts = []
        for slot_idx in range(4):
            slot_k = str(slot_idx)
            phys_num = slot_idx + 1
            tray = self.ams_trays_info.get(slot_k)
            slot_grams = self.get_slot_grams(slot_k)
            if not tray or tray.get("empty", False) or not tray.get("type") or str(tray.get("type", "")).lower() == "empty" or slot_grams <= 0:
                parts.append(f"Слот {phys_num}: порожній")
            else:
                t_type = tray.get("type")
                t_color = tray.get("color", "")
                color_str = f" ({t_color})" if t_color else ""
                remain = tray.get("remain", -1)
                remain_str = f" [{remain}%]" if remain >= 0 else ""
                parts.append(f"Слот {phys_num}: {t_type}{color_str}{remain_str}")
        return " | ".join(parts)

    def get_loaded_filaments(self) -> list[dict[str, Any]]:
        """Returns list of all non-empty loaded slots (AMS 0..3 and External 254)."""
        res = []
        for slot_k in ["0", "1", "2", "3", "254"]:
            t_info = self.ams_trays_info.get(slot_k)
            slot_grams = self.get_slot_grams(slot_k)
            if t_info and not t_info.get("empty", False) and slot_grams > 0:
                t_type = str(t_info.get("type") or t_info.get("tray_type") or "").strip()
                if t_type and t_type.lower() != "empty":
                    res.append({
                        "slot_id": slot_k,
                        "physical_slot": int(slot_k) + 1 if slot_k != "254" else "Зовнішня",
                        "type": t_type,
                        "color": t_info.get("color", ""),
                        "remain": t_info.get("remain", -1),
                    })
        return res

    def get_notify_dict(self) -> dict[str, Any]:
        """Returns normalized notification settings dictionary for this printer."""
        if isinstance(self.notify, dict):
            return {
                "start": bool(self.notify.get("start", True)),
                "finish": bool(self.notify.get("finish", True)),
                "pause": bool(self.notify.get("pause", True)),
                "hms": bool(self.notify.get("hms", True)),
                "remind_clear": bool(self.notify.get("remind_clear", True)),
                "min_time_to_end": int(self.notify.get("min_time_to_end", 0)),
                "min_filament": int(self.notify.get("min_filament", 0)),
            }
        is_on = bool(self.notify)
        return {
            "start": is_on,
            "finish": is_on,
            "pause": is_on,
            "hms": is_on,
            "remind_clear": is_on,
            "min_time_to_end": 0,
            "min_filament": 0,
        }

    def get_active_spool_key(self) -> str | None:
        """
        Returns key of active slot ("0".."3" for AMS, "254" for External vt_tray),
        or None if idle (255 / no active spool loaded). Checks both active_ams_tray and target_ams_tray.
        """
        tray = getattr(self, "active_ams_tray", 255)
        if tray is not None and tray != 255:
            if tray == 254:
                return AMSSlot.EXTERNAL.value  # "254"
            if 0 <= tray <= 15:
                return str(tray)  # "0".."3"

        tar_tray = getattr(self, "target_ams_tray", None)
        if tar_tray is not None and tar_tray != 255:
            if tar_tray == 254:
                return AMSSlot.EXTERNAL.value
            if 0 <= tar_tray <= 15:
                return str(tar_tray)

        return None

    @property
    def is_online(self) -> bool:
        """Checks if the printer is actively connected and responding to MQTT telemetry."""
        if not getattr(self, "is_mqtt_connected", False):
            return False
        last_time = getattr(self, "last_mqtt_msg_time", 0.0)
        if last_time > 0 and (time.time() - last_time > 90.0):
            return False
        return True

    @property
    def online(self) -> bool:
        return self.is_online

    @property
    def is_printing(self) -> bool:
        """Checks if the printer is actively printing or in prepare/building/pause state."""
        return bool(
            getattr(self, "_is_printing", False)
            or getattr(self, "gcode_state", "") in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PAUSE"]
        )

    @is_printing.setter
    def is_printing(self, val: bool) -> None:
        self._is_printing = bool(val)

    @property
    def filament_grams(self) -> float:
        """Returns the current remaining grams for the active slot or printer."""
        return self.get_slot_grams()

    @filament_grams.setter
    def filament_grams(self, val: float) -> None:
        self._filament_grams = max(0.0, round(float(val), 2))
        s_key = self.get_active_slot_key()
        self.ams_slots[s_key] = self._filament_grams

    def get_active_slot_key(self) -> str:
        """Returns active slot key or falls back to _current_job_slot_key, last_active_slot, '0' (AMS) if printer has AMS, else '254' (External)."""
        key = self.get_active_spool_key()
        if key is not None:
            return key
        curr_job = getattr(self, "_current_job_slot_key", None)
        if curr_job is not None:
            return str(curr_job)
        last = getattr(self, "last_active_slot", None)
        if last is not None:
            return str(last)
        if getattr(self, "has_ams", False):
            return "0"
        return AMSSlot.EXTERNAL.value

    def get_slot_grams(self, slot_id: Any | None = None) -> float:
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        if s_key == "255":
            s_key = AMSSlot.EXTERNAL.value
        val = float(self.ams_slots.get(s_key, getattr(self, "_filament_grams", 1000.0)))
        return max(0.0, round(val, 2))

    def set_slot_grams(self, grams: float, slot_id: Any | None = None) -> None:
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        if s_key == "255":
            s_key = AMSSlot.EXTERNAL.value
        g_val = max(0.0, round(float(grams), 2))
        self.ams_slots[s_key] = g_val
        if s_key == self.get_active_slot_key():
            self._filament_grams = g_val

    def _get_active_event_loop(self) -> asyncio.AbstractEventLoop | None:
        if self._main_loop and self._main_loop.is_running():
            return self._main_loop
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                self._main_loop = loop
                return loop
        except RuntimeError:
            pass
        try:
            loop = asyncio.get_event_loop()
            if loop and loop.is_running():
                self._main_loop = loop
                return loop
        except Exception:
            pass
        return None

    def _deduct_spool_warehouse(self, slot_key: str, deducted_grams: float) -> None:
        """Deducts grams from mounted spool in warehouse storage and logs audit movement."""
        from services.printer_accounting_service import deduct_spool_warehouse

        deduct_spool_warehouse(
            storage=self.storage,
            printer_id=self.id,
            printer_name=self.name,
            slot_key=slot_key,
            deducted_grams=deducted_grams,
            subtask_name=getattr(self, "subtask_name", None),
            loop=self._get_active_event_loop(),
        )

    def _refund_spool_warehouse(self, slot_key: str, refund_grams: float, reason: str = "") -> None:
        """Refunds unprinted grams back to mounted spool in warehouse storage when objects are skipped."""
        from services.printer_accounting_service import refund_spool_warehouse

        refund_spool_warehouse(
            storage=self.storage,
            printer_id=self.id,
            printer_name=self.name,
            slot_key=slot_key,
            refund_grams=refund_grams,
            reason=reason or f"Пропуск об'єктів: {getattr(self, 'subtask_name', None) or 'Завдання'}",
            loop=self._get_active_event_loop(),
        )

    def init_mqtt(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if not self.ip or not self.serial_number:
            logger.warning(f"[{self.name}] Missing IP or Serial, MQTT disabled.")
            return

        if loop is not None:
            self._main_loop = loop
        elif self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        client_uid = f"t_{self.id}"
        try:
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_uid)
        except Exception:
            try:
                self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_uid)
            except Exception:
                self._client = mqtt.Client(client_id=client_uid)
        try:
            acc_code_str = str(self.access_code or "")[:128]
            self._client.username_pw_set("bblp", acc_code_str)
        except Exception as e:
            logger.warning(f"Failed setting username_pw_set for [{self.name}]: {e}")

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self._client.tls_set_context(context)

        self.is_mqtt_connected = False
        self.last_mqtt_msg_time = time.time()

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        setattr(self._client, "on_error", self._on_error)

        self._stop_mqtt = False
        try:
            self._client.connect_async(self.ip, 8883, 60)
            self._client.loop_start()
            logger.info(f"🚀 Initialized MQTT client for [{self.name}] ({self.ip})")
        except Exception as e:
            logger.error(f"❌ Failed connecting MQTT for [{self.name}]: {e}")

    def destroy(self) -> None:
        self._stop_mqtt = True
        if self._client:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            try:
                self._client.disconnect()
            except Exception:
                pass
            logger.info(f"🛑 Disconnected MQTT for [{self.name}]")

    def request_pushall(self) -> None:
        """Requests a full status report from the printer over MQTT."""
        if self._client is not None and getattr(self, "is_mqtt_connected", False) and getattr(self, "serial_number", None):
            try:
                push_req = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}})
                self._client.publish(f"device/{self.serial_number}/request", push_req)
            except Exception as e:
                logger.warning(f"Failed to request pushall for [{self.name}]: {e}")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, *args: Any, **kwargs: Any) -> None:
        rc = args[0] if args else kwargs.get("reason_code", kwargs.get("rc", 0))
        is_success = (rc == 0) or (getattr(rc, "is_failure", False) is False and getattr(rc, "value", 0) == 0)
        if is_success:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            if self.gcode_state in ["OFFLINE", "UNKNOWN", "DISCONNECTED"]:
                self.gcode_state = "IDLE"
            logger.info(f"✅ Connected to Bambu MQTT [{self.name}] ({self.ip})")
            if self.serial_number:
                client.subscribe(f"device/{self.serial_number}/report")
                self.request_pushall()
        else:
            self.is_mqtt_connected = False
            logger.error(f"❌ MQTT connection error [{self.name}] code: {rc}")

    def _on_disconnect(self, client: Any, userdata: Any, *args: Any, **kwargs: Any) -> None:
        rc = args[1] if len(args) >= 2 else (args[0] if args else kwargs.get("reason_code", kwargs.get("rc", 0)))
        self.is_mqtt_connected = False
        self.gcode_state = "OFFLINE"
        logger.warning(f"⚠️ MQTT disconnected for [{self.name}] (code: {rc})")

    def _on_error(self, client: Any, userdata: Any, rc: Any) -> None:
        self.is_mqtt_connected = False
        self.gcode_state = "OFFLINE"
        logger.error(f"❌ MQTT error [{self.name}]: {rc}")

    def _trigger_save(self) -> None:
        if self.save_callback:
            try:
                loop_to_use = self._get_active_event_loop()
                if loop_to_use:
                    if asyncio.iscoroutinefunction(self.save_callback):
                        asyncio.run_coroutine_threadsafe(self.save_callback(), loop_to_use)
                    else:
                        loop_to_use.call_soon_threadsafe(self.save_callback)
            except Exception as e:
                logger.warning(f"Failed triggering save callback for [{self.name}]: {e}")

    def _try_ftps_fetch(self) -> None:
        from services.printer_file_job_service import fetch_job_info_via_ftps

        fetch_job_info_via_ftps(self)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        payload = msg.payload
        self._process_message(payload)

    def _process_message(self, payload: bytes) -> None:
        try:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            if self.gcode_state in ["OFFLINE", "UNKNOWN", "DISCONNECTED"]:
                self.gcode_state = "IDLE"
            parsed = parse_mqtt_payload(payload)
            if not parsed:
                return

            print_data = parsed["print_data"]
            if "gcode_state" in parsed:
                self.gcode_state = parsed["gcode_state"]
            if "nozzle_temper" in parsed:
                self.nozzle_temper = parsed["nozzle_temper"]
            if "nozzle_target_temper" in parsed:
                self.nozzle_target_temper = parsed["nozzle_target_temper"]
            if "bed_temper" in parsed:
                self.bed_temper = parsed["bed_temper"]
            if "bed_target_temper" in parsed:
                self.bed_target_temper = parsed["bed_target_temper"]
            if "chamber_temper" in parsed:
                self.chamber_temper = parsed["chamber_temper"]
            if "wifi_signal" in parsed:
                self.wifi_signal = parsed["wifi_signal"]
            if "gcode_start_time" in parsed:
                self.gcode_start_time = parsed["gcode_start_time"]
            if "print_error" in parsed:
                self.print_error = parsed["print_error"]
            if "mc_print_error_code" in parsed:
                self.mc_print_error_code = parsed["mc_print_error_code"]
            if "fail_reason" in parsed:
                self.fail_reason = parsed["fail_reason"]
            if "hw_switch_state" in parsed:
                self.hw_switch_state = parsed["hw_switch_state"]
            if "nozzle_diameter" in parsed:
                self.nozzle_diameter = parsed["nozzle_diameter"]
            if "ams_status" in parsed:
                self.ams_status = parsed["ams_status"]
            if "tray_exist_bits" in parsed:
                self.tray_exist_bits = parsed["tray_exist_bits"]
            if "xcam_info" in parsed:
                self.xcam_info = parsed["xcam_info"]
            if "upgrade_state" in parsed:
                self.upgrade_state = parsed["upgrade_state"]
            if "upload_info" in parsed:
                self.upload_info = parsed["upload_info"]
            if "mc_percent" in parsed:
                self.mc_percent = parsed["mc_percent"]
            if "mc_remaining_time" in parsed:
                self.mc_remaining_time = parsed["mc_remaining_time"]
            if "layer_num" in parsed:
                self.layer_num = parsed["layer_num"]
            if "total_layer_num" in parsed:
                self.total_layer_num = parsed["total_layer_num"]
            if "subtask_name" in parsed:
                self.subtask_name = parsed["subtask_name"]
            if "spd_lvl" in parsed:
                self.spd_lvl = parsed["spd_lvl"]
            if "spd_mag" in parsed:
                self.spd_mag = parsed["spd_mag"]
            if "chamber_light_state" in parsed:
                self.chamber_light_state = parsed["chamber_light_state"]
            if "hms_errors" in parsed:
                self.hms_errors = parsed["hms_errors"]
                self.hms_resolved = parsed.get("hms_resolved") or format_hms_errors(self.hms_errors)
            if "skipped_objects" in parsed:
                new_skipped = parsed["skipped_objects"]
                if new_skipped != self.skipped_objects:
                    curr_pct = max(0, min(100, int(getattr(self, "mc_percent", getattr(self, "progress", 0)) or 0)))
                    skipped_at = getattr(self, "_skipped_at_progress", None)
                    if not isinstance(skipped_at, dict):
                        skipped_at = {}
                        self._skipped_at_progress = skipped_at
                    for oid in new_skipped:
                        if isinstance(oid, int) and oid not in skipped_at:
                            skipped_at[oid] = curr_pct
                    self.skipped_objects = new_skipped
                    self.invalidate_plate_gif_cache()

            if "has_ams" in parsed:
                self._has_ams_telemetry = parsed["has_ams"]
            if "ams_exist_bits" in parsed:
                self.ams_exist_bits = parsed["ams_exist_bits"]
            if "tray_tar" in parsed:
                try:
                    self.target_ams_tray = int(parsed["tray_tar"])
                    if self.target_ams_tray != 255:
                        self.last_active_slot = str(self.target_ams_tray)
                except (ValueError, TypeError):
                    pass
            if "active_ams_tray" in parsed:
                self.active_ams_tray = parsed["active_ams_tray"]
                if self.active_ams_tray is not None and self.active_ams_tray != 255:
                    self.last_active_slot = str(self.active_ams_tray)
            if "ams_units" in parsed:
                self.ams_units = parsed["ams_units"]
            if parsed.get("has_ams") is False or getattr(self, "ams_exist_bits", "") in ["0", "0000"]:
                self.ams_trays_info = {k: v for k, v in self.ams_trays_info.items() if k in ["254", "255"]}
            elif "ams_trays_info" in parsed:
                self.ams_trays_info.update(parsed["ams_trays_info"])
            if "ams_humidity_idx" in parsed:
                self.ams_humidity_idx = parsed["ams_humidity_idx"]
            if "ams_humidity_raw" in parsed:
                self.ams_humidity_raw = parsed["ams_humidity_raw"]
            if "ams_temp" in parsed:
                self.ams_temp = parsed["ams_temp"]

            # Step 1: Raw AMS Telemetry Logging for real data verification
            if "ams" in print_data and isinstance(print_data["ams"], dict):
                ams_data = print_data["ams"]
                t_now = ams_data.get("tray_now")
                t_pre = ams_data.get("tray_pre")
                t_tar = ams_data.get("tray_tar")
                if t_tar is not None:
                    try:
                        self.target_ams_tray = int(t_tar)
                        if self.target_ams_tray != 255:
                            self.last_active_slot = str(self.target_ams_tray)
                    except (ValueError, TypeError):
                        pass
                if t_now is not None:
                    try:
                        self.active_ams_tray = int(t_now)
                        if self.active_ams_tray != 255:
                            self.last_active_slot = str(self.active_ams_tray)
                    except (ValueError, TypeError):
                        pass
                if t_now is not None or t_pre is not None or t_tar is not None:
                    logger.info(
                        f"🔍 [AMS Telemetry] [{self.name}] tray_now={t_now}, tray_pre={t_pre}, tray_tar={t_tar}, exist_bits={ams_data.get('ams_exist_bits')}"
                    )

            # Step 2: Delta-detection of AMS slot changes (spool insertion / removal)
            old_slots = dict(getattr(self, "_previous_ams_slots", {}) or dict(self.ams_slots))
            for slot_key, new_weight in self.ams_slots.items():
                old_weight = old_slots.get(slot_key, 0.0)
                if old_weight == 0.0 and new_weight > 0.0:
                    logger.info(f"[AMS] Нова котушка вставлена в слот {slot_key} на {self.name} ({new_weight}g)")
                elif old_weight > 0.0 and new_weight == 0.0:
                    logger.info(f"[AMS] Котушку витягнуто зі слоту {slot_key} на {self.name}")
            self._previous_ams_slots = dict(self.ams_slots)

            if "vt_tray_info" in parsed:
                self.ams_trays_info["254"] = parsed["vt_tray_info"]

            # Step 2b: Automatic hardware tray load/unload delta detection
            self._check_tray_state_deltas()

            filament = None
            if self.active_ams_tray == 254 or not self.has_ams:
                filament = print_data.get("vt_tray", {}).get("tray_type")
            elif self.active_ams_tray in [0, 1, 2, 3]:
                if self.ams_units:
                    for ams_b in self.ams_units:
                        for tray in ams_b.get("tray", []):
                            if str(tray.get("id")) == str(self.active_ams_tray) and tray.get("tray_type"):
                                filament = tray.get("tray_type")
                                break
                if not filament and str(self.active_ams_tray) in self.ams_trays_info:
                    tray_info = self.ams_trays_info[str(self.active_ams_tray)]
                    filament = tray_info.get("type") or tray_info.get("tray_type")
            if filament:
                self.filament_type = filament

            # Subtask change & calibration tracking
            curr_subtask = str(self.subtask_name or "").strip()
            calib_keywords = [
                "calib", "calibration", "g32", "g29", "leveling", "bed_level",
                "vibration", "resonance", "flow_cali", "motor_noise", "noise_cali"
            ]
            raw_gcode_file = str(print_data.get("gcode_file") or print_data.get("gcode_file_prepare") or "").lower()
            print_type_str = str(print_data.get("print_type") or "").lower()

            is_calib_name = (
                any(k in curr_subtask.lower() for k in calib_keywords)
                or any(k in raw_gcode_file for k in calib_keywords)
                or print_type_str in ["cali", "calibration"]
            )
            if is_calib_name:
                self._is_calibrating = True

            if getattr(self, "_is_calibrating", False):
                self._job_deducted = True
                self._current_job_grams = 0.0

            if curr_subtask and curr_subtask != getattr(self, "_last_subtask_name", ""):
                if getattr(self, "_last_subtask_name", "") != "":
                    if not getattr(self, "_is_calibrating", False) and not getattr(self, "_job_started_from_app", False):
                        logger.info(
                            f"🔄 Subtask changed for [{self.name}]: '{getattr(self, '_last_subtask_name', '')}' -> '{curr_subtask}'. Resetting job weight."
                        )
                        self._current_job_grams = 0.0
                        self._job_deducted = False
                self._last_subtask_name = curr_subtask

            if self.gcode_state in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PAUSE"]:
                if not self._is_printing:
                    self._is_printing = True
                    if not getattr(self, "_job_started_from_app", False) and not getattr(self, "_is_calibrating", False):
                        self._current_job_grams = 0.0
                        self._job_deducted = False
                self._was_running = True
                self._history_recorded = False
                if getattr(self, "job_start_time", 0.0) == 0.0:
                    self.job_start_time = time.time()

            # Always sync active slot weight to printer's main filament_grams property
            self.filament_grams = self.get_slot_grams()

            # Extract model weight only for real print jobs (when NOT calibrating)
            total_layers_count = int(getattr(self, "total_layer_num", 0) or 0)
            if not getattr(self, "_is_calibrating", False):
                w_val = extract_model_weight(print_data)
                if w_val > 0 and self._current_job_grams == 0.0:
                    self._current_job_grams = w_val

                # Check OrcaSlicer cache file if weight is still 0.0 (strictly require real print with layers)
                if self._current_job_grams == 0.0 and total_layers_count > 0:
                    c_data = None
                    if hasattr(self, "storage") and hasattr(self.storage, "get_sliced_weight_cache_sync"):
                        c_data = self.storage.get_sliced_weight_cache_sync()
                    if c_data is None:
                        cache_file = STORAGE_DIR / "last_sliced_weight.json"
                        if cache_file.exists():
                            try:
                                c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                            except Exception:
                                pass
                    if c_data:
                        try:
                            c_w = float(c_data.get("weight", 0.0))
                            c_ts = float(c_data.get("timestamp", 0.0))
                            c_fname = str(c_data.get("filename") or c_data.get("path") or "").strip().lower()
                            s_name = str(self.subtask_name or "").strip().lower()
                            clean_c = re.sub(r"\.(gcode|3mf)$", "", c_fname).replace("\\", "/").split("/")[-1]
                            clean_s = re.sub(r"\.(gcode|3mf)$", "", s_name).replace("\\", "/").split("/")[-1]

                            fname_match = bool(clean_c and clean_s and clean_s != "untitled" and (clean_c in clean_s or clean_s in clean_c))
                            recent_slice = bool(c_ts > 0 and (time.time() - c_ts < 300) and (not clean_s or clean_s == "untitled"))
                            if (c_w > 0 or "objects" in c_data) and (fname_match or recent_slice):
                                if c_w > 0:
                                    self._current_job_grams = c_w
                                if isinstance(c_data.get("objects"), list) and c_data["objects"]:
                                    self.current_job_objects = c_data["objects"]
                                    logger.info(f"🧩 Loaded {len(self.current_job_objects)} cached objects for [{self.name}]")
                                logger.info(f"💡 Loaded OrcaSlicer cached weight {c_w}g for [{self.name}] (matched '{clean_c}')")
                        except Exception as e:
                            logger.warning(f"Error reading OrcaSlicer weight cache: {e}")

                # Check subtask filename regex if weight is still 0.0 (only when printing a file with layers or explicitly started)
                if self._current_job_grams == 0.0 and self.subtask_name and (total_layers_count > 0 or getattr(self, "_job_started_from_app", False)):
                    w_fname = extract_subtask_weight(self.subtask_name)
                    if w_fname > 0:
                        self._current_job_grams = w_fname
                        logger.info(f"💡 Extracted weight {w_fname}g from subtask_name for [{self.name}]")

            # Trigger FTPS fetch to download 3MF/gcode from printer SD card and extract exact weight/objects from slice_info.config / .gcode
            if (
                self.gcode_state in ["RUNNING", "PAUSE"]
                and not getattr(self, "_is_calibrating", False)
                and (self._current_job_grams == 0.0 or not self.current_job_objects)
            ):
                now_ts = time.time()
                if (
                    not self._ftps_fetching
                    and getattr(self, "_ftps_attempts", 0) < 5
                    and (now_ts - getattr(self, "_last_ftps_time", 0.0) >= 8.0)
                ):
                    self._ftps_attempts = getattr(self, "_ftps_attempts", 0) + 1
                    self._last_ftps_time = now_ts
                    self._try_ftps_fetch()

            if self.gcode_state in ["RUNNING", "PAUSE", "PREPARATION", "BUILDING"] and not self.current_job_objects:
                skipped = getattr(self, "skipped_objects", [])
                skipped_ids = sorted(list({int(x) for x in skipped if str(x).isdigit()}))
                if skipped_ids:
                    self.current_job_objects = [
                        {"id": str(oid), "name": f"Об'єкт #{oid}", "_synthetic": True}
                        for oid in skipped_ids[:50]
                    ]

            if self.gcode_state in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PAUSE"]:
                is_calib = bool(getattr(self, "_is_calibrating", False))
                total_layers = int(getattr(self, "total_layer_num", 0) or 0)
                is_completed_duplicate = bool(
                    self.subtask_name
                    and self.subtask_name == getattr(self, "_last_completed_subtask", None)
                    and total_layers <= 0
                )
                has_real_file = bool(
                    self.subtask_name
                    and any(str(self.subtask_name).lower().endswith(ext) for ext in [".3mf", ".gcode"])
                    and not is_calib
                )
                is_valid_print_job = (
                    not is_calib
                    and not is_completed_duplicate
                    and (total_layers > 0 or has_real_file or getattr(self, "_job_started_from_app", False))
                )

                if (
                    is_valid_print_job
                    and self._current_job_grams > 0
                    and not self._job_deducted
                ):
                    active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_spool_key() or getattr(self, "last_active_slot", None)
                    if active_key is None and not getattr(self, "has_ams", False):
                        active_key = AMSSlot.EXTERNAL.value
                    if active_key is None:
                        logger.warning(
                            f"[{self.name}] Немає активного слоту (idle / active_ams_tray={self.active_ams_tray}, target={getattr(self, 'target_ams_tray', None)}) — автосписання ваги пропущено."
                        )
                    else:
                        old_w = self.get_slot_grams(active_key)
                        new_w = max(0.0, round(old_w - self._current_job_grams, 2))
                        self.set_slot_grams(new_w, active_key)
                        self._job_deducted = True
                        self.last_job_grams = self._current_job_grams
                        self._deduct_spool_warehouse(active_key, self._current_job_grams)
                        logger.info(
                            f"💾 Auto-deducted {self._current_job_grams}g from Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g"
                        )
                        self._trigger_save()

                if self.subtask_name and is_valid_print_job:
                    curr_p = int(self.mc_percent or 0)
                    if curr_p < 100 and self.gcode_state not in ["FINISH", "SUCCESS"]:
                        now_ts = time.time()
                        last_l = getattr(self, "_last_saved_context_layer", -1)
                        last_p = getattr(self, "_last_saved_context_progress", -1)
                        last_t = getattr(self, "_last_saved_context_time", 0.0)

                        progress_delta = abs(curr_p - last_p)
                        layer_delta = abs((self.layer_num or 0) - last_l)
                        time_elapsed = now_ts - last_t

                        should_save = (
                            last_p < 0
                            or progress_delta >= 2
                            or (self.total_layer_num > 0 and layer_delta >= 5)
                            or time_elapsed >= 900.0
                        )
                        if should_save:
                            from utils.spool_fingerprint import build_spool_fingerprint, save_active_print_context

                            active_print_context = {
                                "printer_id": self.id,
                                "subtask_name": self.subtask_name,
                                "total_layers": self.total_layer_num,
                                "saved_layer": self.layer_num,
                                "saved_progress": self.mc_percent,
                                "spool_fingerprint": build_spool_fingerprint(self),
                                "job_grams": self._current_job_grams,
                                "job_deducted": self._job_deducted,
                                "skipped_at_progress": getattr(self, "_skipped_at_progress", {}),
                                "timestamp": now_ts,
                            }
                            save_active_print_context(self.id, active_print_context)
                            self._has_active_context = True
                            self._last_saved_context_layer = self.layer_num
                            self._last_saved_context_progress = curr_p
                            self._last_saved_context_time = now_ts

            elif self.gcode_state in ["FINISH", "IDLE", "FAILED", "SUCCESS", "CANCEL"]:
                was_calibrating = bool(getattr(self, "_is_calibrating", False))
                total_layers = int(getattr(self, "total_layer_num", 0) or 0)
                is_completed_duplicate = bool(
                    self.subtask_name
                    and self.subtask_name == getattr(self, "_last_completed_subtask", None)
                    and total_layers <= 0
                )

                if was_calibrating or is_completed_duplicate:
                    self._job_deducted = True
                    self._current_job_grams = 0.0
                    self._is_printing = False
                    self._was_running = False
                    self._history_recorded = True
                    self._is_calibrating = False

                was_active = (
                    self._is_printing
                    or getattr(self, "_was_running", False)
                    or getattr(self, "_job_started_from_app", False)
                )
                has_real_file = bool(
                    self.subtask_name
                    and any(str(self.subtask_name).lower().endswith(ext) for ext in [".3mf", ".gcode"])
                    and not was_calibrating
                )
                is_valid_finish = (
                    (total_layers > 0 or has_real_file or getattr(self, "_job_started_from_app", False))
                    and not was_calibrating
                    and not is_completed_duplicate
                )
                should_record_history = was_active and not getattr(self, "_history_recorded", False) and is_valid_finish

                if (self.gcode_state == "FINISH" or should_record_history) and is_valid_finish:
                    if not self._job_deducted:
                        if self._current_job_grams == 0.0 and total_layers > 0:
                            c_data = None
                            if hasattr(self, "storage") and hasattr(self.storage, "get_sliced_weight_cache_sync"):
                                c_data = self.storage.get_sliced_weight_cache_sync()
                            if c_data is None:
                                cache_file = STORAGE_DIR / "last_sliced_weight.json"
                                if cache_file.exists():
                                    try:
                                        c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                                    except Exception:
                                        pass
                            if c_data:
                                try:
                                    c_w = float(c_data.get("weight", 0.0))
                                    c_ts = float(c_data.get("timestamp", 0.0))
                                    c_fname = str(c_data.get("filename") or c_data.get("path") or "").strip().lower()
                                    s_name = str(self.subtask_name or "").strip().lower()
                                    clean_c = re.sub(r"\.(gcode|3mf)$", "", c_fname).replace("\\", "/").split("/")[-1]
                                    clean_s = re.sub(r"\.(gcode|3mf)$", "", s_name).replace("\\", "/").split("/")[-1]

                                    fname_match = bool(clean_c and clean_s and clean_s != "untitled" and (clean_c in clean_s or clean_s in clean_c))
                                    recent_slice = bool(c_ts > 0 and (time.time() - c_ts < 300) and (not clean_s or clean_s == "untitled"))
                                    if c_w > 0 and (fname_match or recent_slice):
                                        self._current_job_grams = c_w
                                except Exception:
                                    pass

                        if self._current_job_grams == 0.0 and self.subtask_name:
                            m_fname = re.search(
                                r"(?:_|\b)(\d+(?:[\.,]\d+)?)\s*(?:g|г|gram|grams)\b", self.subtask_name, re.IGNORECASE
                            )
                            if m_fname:
                                try:
                                    val = float(m_fname.group(1).replace(",", "."))
                                    if 0.0 < val < 5000.0:
                                        self._current_job_grams = val
                                except Exception:
                                    pass

                        if self._current_job_grams > 0:
                            active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            final_weight, _ = self.calculate_effective_job_grams(self._current_job_grams)
                            new_w = max(0.0, round(old_w - final_weight, 2))
                            self.set_slot_grams(new_w, active_key)
                            self._job_deducted = True
                            self._skip_refund_applied = True
                            self.last_job_grams = final_weight
                            self._deduct_spool_warehouse(active_key, final_weight)
                            logger.info(
                                f"💾 Auto-deducted {final_weight}g from AMS Slot {active_key} for [{self.name}] on job completion. Old: {old_w}g -> New: {new_w}g"
                            )
                            self._trigger_save()
                    elif (
                        self._current_job_grams > 0
                        and getattr(self, "skipped_objects", None)
                        and not getattr(self, "_skip_refund_applied", False)
                    ):
                        effective_w, saved_w = self.calculate_effective_job_grams(self._current_job_grams)
                        self._skip_refund_applied = True
                        if saved_w > 0:
                            active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            new_w = round(old_w + saved_w, 2)
                            self.set_slot_grams(new_w, active_key)
                            self.last_job_grams = effective_w
                            self._refund_spool_warehouse(
                                active_key,
                                saved_w,
                                reason=f"Пропуск об'єктів ({len(self.skipped_objects)} шт.): {self.subtask_name or 'Завдання'}",
                            )
                            logger.info(
                                f"♻️ Auto-refunded {saved_w}g to Slot {active_key} for [{self.name}] due to skipped objects {self.skipped_objects}. Effective weight: {effective_w}g"
                            )
                            self._trigger_save()

                    if self.finish_timestamp == 0.0:
                        self.finish_timestamp = time.time()

                    if should_record_history and is_valid_finish:
                        logger.info(f"🎉 Print finished/completed on [{self.name}] (state: {self.gcode_state})!")
                        final_weight = getattr(self, "last_job_grams", 0.0) or getattr(self, "_current_job_grams", 0.0) or 0.0
                        if final_weight == 0.0 and self.subtask_name:
                            final_weight = extract_subtask_weight(self.subtask_name)

                        if final_weight == 0.0:
                            c_data = None
                            if hasattr(self, "storage") and hasattr(self.storage, "get_sliced_weight_cache_sync"):
                                c_data = self.storage.get_sliced_weight_cache_sync()
                            if c_data is None:
                                cache_file = STORAGE_DIR / "last_sliced_weight.json"
                                if cache_file.exists():
                                    try:
                                        c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                                    except Exception:
                                        pass
                            if c_data:
                                try:
                                    c_w = float(c_data.get("weight", 0.0))
                                    if c_w > 0:
                                        final_weight = c_w
                                except Exception:
                                    pass

                        if final_weight > 0 and getattr(self, "skipped_objects", None) and not getattr(self, "_skip_refund_applied", False):
                            final_weight, _ = self.calculate_effective_job_grams(final_weight)

                        note_text = "Завершено"
                        if getattr(self, "skipped_objects", None):
                            skipped_str = ", ".join(f"#{s}" for s in self.skipped_objects[:10])
                            note_text = f"Завершено (Пропущено об'єктів: {len(self.skipped_objects)} [{skipped_str}])"

                        raw_title = getattr(self, "_custom_job_name", None) or str(self.subtask_name or "").strip()
                        raw_title = raw_title.replace("Metadata/", "").replace("metadata/", "").strip()
                        if "." in raw_title and not raw_title.endswith((".3mf", ".gcode")):
                            raw_title = raw_title.rsplit(".", 1)[0]
                        elif raw_title.endswith((".3mf", ".gcode")):
                            raw_title = raw_title.rsplit(".", 1)[0]

                        clean_subtask = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_title).strip()
                        if not clean_subtask or clean_subtask.lower() in ["untitled", "none", "null"] or re.match(r"^[_ -]+$", clean_subtask):
                            clean_subtask = "Деталь 3D"

                        from services.printer_accounting_service import record_print_history_entry

                        record_print_history_entry(
                            storage=self.storage,
                            printer=self,
                            final_weight=final_weight,
                            note_text=note_text,
                            loop=self._get_active_event_loop(),
                        )
                        self._last_completed_subtask = str(self.subtask_name or "").strip()
                        self._history_recorded = True
                        self._is_printing = False
                        self._was_running = False
                        self._job_started_from_app = False
                        self._has_active_context = False

                    self._is_printing = False

                if self.gcode_state in ["IDLE", "FAILED", "FINISH", "SUCCESS", "CANCEL"]:
                    if getattr(self, "_has_active_context", True):
                        from utils.spool_fingerprint import delete_active_print_context

                        delete_active_print_context(self.id)
                        self._has_active_context = False
                    # Reset state counters & job objects for next job
                    self.finish_timestamp = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self.finish_timestamp
                    self.job_start_time = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self.job_start_time
                    self.current_job_objects = []
                    self.skipped_objects = []
                    self._skipped_at_progress = {}
                    self._skip_refund_applied = False
                    self._plate_gif_cache = None
                    self._is_printing = False
                    self._was_running = False
                    self._job_started_from_app = False
                    self._has_active_context = False
                    self._job_deducted = False if self.gcode_state in ["IDLE", "FAILED"] else self._job_deducted
                    self._ftps_attempted = False
                    self._ftps_attempts = 0
                    self._last_ftps_time = 0.0
                    self._current_job_grams = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self._current_job_grams
                    self._history_recorded = False if self.gcode_state in ["IDLE", "FAILED"] else self._history_recorded
                    if self.gcode_state in ["IDLE", "FAILED"]:
                        self._is_calibrating = False
                        self._current_job_slot_key = None

        except Exception as e:
            logger.error(f"Error processing MQTT message for [{self.name}]: {e}")

    # Hardware control commands & maintenance tracking inherited via PrinterCommandsMixin and PrinterMaintenanceMixin

    @property
    def mapped_state(self) -> str:
        """Maps internal gcode_state into 4 canonical user-facing states: RUNNING, PAUSE, ONLINE, OFFLINE."""
        if not getattr(self, "is_online", True):
            return "OFFLINE"
        st = str(self.gcode_state or "ONLINE").upper()
        if st in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PRINTING", "SLICING", "BUSY", "CHANGING_FILAMENT", "MAM_CLEANING"]:
            return "RUNNING"
        if st in ["PAUSE", "PAUSED"]:
            return "PAUSE"
        if st in ["OFFLINE", "DISCONNECTED", "UNKNOWN"]:
            return "ONLINE" if getattr(self, "is_online", False) else "OFFLINE"
        return "ONLINE"

    def to_dict(self, for_storage: bool = False) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "accessCode": self.access_code if for_storage else ("••••••••" if self.access_code else ""),
            "serialNumber": self.serial_number,
            "printer_model": getattr(self, "printer_model", "A1"),
            "spoolDbFile": self.spool_db_file,
            "filament_grams": self.filament_grams,
            "notify": self.notify,
            "log": self.log,
            "price_per_kg": self.price_per_kg,
            "power_watts": self.power_watts,
            "electricity_rate_uah": self.electricity_rate_uah,
            "active_spool_id": self.active_spool_id,
            "total_print_hours": self.total_print_hours,
            "maintenance_hours_counter": self.maintenance_hours_counter,
            "maintenance_interval_hours": self.maintenance_interval_hours,
            "last_maintenance_timestamp": self.last_maintenance_timestamp,
            "maintenance_items": self.maintenance_items,
            "gcode_state": self.gcode_state if for_storage else self.mapped_state,
            "raw_gcode_state": self.gcode_state,
            "nozzle_temper": self.nozzle_temper,
            "nozzle_target_temper": self.nozzle_target_temper,
            "bed_temper": self.bed_temper,
            "bed_target_temper": self.bed_target_temper,
            "chamber_temper": self.chamber_temper,
            "wifi_signal": self.wifi_signal,
            "gcode_start_time": self.gcode_start_time,
            "print_error": self.print_error,
            "mc_print_error_code": self.mc_print_error_code,
            "fail_reason": self.fail_reason,
            "hw_switch_state": self.hw_switch_state,
            "nozzle_diameter": self.nozzle_diameter,
            "ams_status": self.ams_status,
            "tray_exist_bits": self.tray_exist_bits,
            "xcam_info": self.xcam_info,
            "upgrade_state": self.upgrade_state,
            "upload_info": self.upload_info,
            "mc_percent": self.mc_percent,
            "mc_remaining_time": self.mc_remaining_time,
            "layer_num": self.layer_num,
            "total_layer_num": self.total_layer_num,
            "subtask_name": self.subtask_name,
            "filament_type": self.filament_type,
            "spd_lvl": self.spd_lvl,
            "spd_mag": self.spd_mag,
            "ams_slots": self.ams_slots,
            "ams_humidity_idx": self.ams_humidity_idx,
            "ams_temp": self.ams_temp,
            "ams_trays_info": self.ams_trays_info,
            "has_ams": self.has_ams,
            "ams_enabled": self.ams_enabled,
            "ams_units": self.ams_units,
            "hms_errors": self.hms_errors,
            "hms_resolved": self.hms_resolved,
            "chamber_light_state": self.chamber_light_state,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Returns unmasked dictionary representation for internal SQLite / JSON storage persistence."""
        return self.to_dict(for_storage=True)

    def get_active_errors(self) -> list[str]:
        """
        Returns a list of human-readable active error descriptions for this printer.
        Includes resolved HMS errors, MC error codes, print error codes, and fail reason.
        """
        errors: list[str] = []
        if getattr(self, "hms_resolved", None):
            for h in self.hms_resolved:
                s = str(h).strip()
                if s and s not in errors:
                    errors.append(s)
        elif getattr(self, "hms_errors", None):
            for e in self.hms_errors:
                s = str(e).strip()
                if s and s not in errors:
                    errors.append(s)

        mc_err = getattr(self, "mc_print_error_code", None)
        if mc_err is not None:
            mc_str = str(mc_err).strip()
            if mc_str and mc_str not in ["0", "None", "null", ""] and mc_err != 0:
                decoded_mc = decode_print_error(mc_err)
                desc = f"Помилка MC: {decoded_mc} (код: {mc_str})" if decoded_mc else f"Код помилки MC: {mc_str}"
                if desc not in errors:
                    errors.append(desc)

        p_err = getattr(self, "print_error", None)
        if p_err is not None:
            p_str = str(p_err).strip()
            if p_str and p_str not in ["0", "None", "null", ""] and p_err != 0:
                decoded_p = decode_print_error(p_err)
                desc = f"Помилка друку: {decoded_p} (код: {p_str})" if decoded_p else f"Код помилки друку: {p_str}"
                if desc not in errors:
                    errors.append(desc)

        fail_r = getattr(self, "fail_reason", None)
        if fail_r is not None:
            fail_str = str(fail_r).strip()
            if fail_str and fail_str not in ["0", "None", "null", ""] and fail_r != 0:
                desc = f"Причина збою: {fail_str}"
                if desc not in errors:
                    errors.append(desc)

        return errors

    def find_ams_backup_slots(self, required_type: str | None = None) -> list[dict[str, Any]]:
        """
        Finds compatible backup AMS slots that have remaining filament of the same material type.
        Returns a list of dicts: [{"slot": "1", "name": "A2", "grams": 800.0, "type": "PLA", "color": "#FFFFFF"}, ...]
        """
        if not getattr(self, "has_ams", False):
            return []

        active_slot = self.get_active_slot_key() or getattr(self, "last_active_slot", None)
        if str(active_slot) == "254":
            return []  # AMS cannot auto-replace external spool
        slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}

        backups: list[dict[str, Any]] = []
        target_type = (required_type or getattr(self, "filament_type", "") or "").strip().upper()
        if not target_type or target_type in ["НЕВИЗНАЧЕНО", "UNKNOWN"]:
            return []

        # Check all AMS slots except the active one
        for slot_k in ["0", "1", "2", "3"]:
            if active_slot is not None and str(slot_k) == str(active_slot):
                continue
            grams = float(self.ams_slots.get(slot_k, 0.0) or 0.0)
            if grams <= 0:
                continue

            tray_info = self.ams_trays_info.get(slot_k, {})
            tray_type = str(tray_info.get("type") or tray_info.get("tray_type") or "").strip().upper()

            # Check if material type matches (e.g. PLA in PLA Basic, PLA == PLA, PETG == PETG)
            if tray_type and (tray_type == target_type or target_type in tray_type or tray_type in target_type):
                backups.append({
                    "slot": slot_k,
                    "name": slot_names.get(slot_k, f"A{int(slot_k)+1}"),
                    "grams": round(grams, 1),
                    "type": tray_type,
                    "color": tray_info.get("color") or tray_info.get("tray_color") or "",
                })

        return backups

    def flush_active_print_context(self) -> None:
        """Immediately flushes active print context to disk if a valid print is in progress."""
        if not getattr(self, "subtask_name", None) or getattr(self, "gcode_state", "") not in ["RUNNING", "PAUSE", "PREPARE"]:
            return
        try:
            from utils.spool_fingerprint import build_spool_fingerprint, save_active_print_context
            now_ts = time.time()
            active_print_context = {
                "printer_id": self.id,
                "subtask_name": self.subtask_name,
                "total_layers": self.total_layer_num,
                "saved_layer": self.layer_num,
                "saved_progress": self.mc_percent,
                "spool_fingerprint": build_spool_fingerprint(self),
                "job_grams": self._current_job_grams,
                "job_deducted": self._job_deducted,
                "timestamp": now_ts,
            }
            save_active_print_context(self.id, active_print_context)
            self._last_saved_context_layer = self.layer_num
            self._last_saved_context_progress = int(self.mc_percent or 0)
            self._last_saved_context_time = now_ts
            logger.info(f"💾 Flushed active print context for [{self.name}] to disk")
        except Exception as e:
            logger.warning(f"Failed to flush active print context for [{self.name}]: {e}")
