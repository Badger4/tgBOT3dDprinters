"""
Bambu Lab 3D Printer MQTT client and domain model.
"""

import asyncio
import hashlib
import html
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
from services.ftps_client import extract_model_weight, fetch_bambu_ftps_weight, upload_3mf_to_bambu, verify_bambu_file_size
from services.gcode_parser import parse_3mf_file
from services.hms_resolver import format_hms_errors
from services.mqtt_message_parser import extract_subtask_weight, parse_mqtt_payload
from storage.manager import StorageManager

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


class BambuPrinter:
    """Manages Bambu Lab 3D Printer telemetry and MQTT control."""

    def __init__(self, config: dict[str, Any], storage: StorageManager, save_callback: Any | None = None):
        self.id = str(config.get("id") or uuid.uuid4())
        self.name = config.get("name", "Bambu Printer")
        self.ip = config.get("ip", "")
        raw_code = config.get("accessCode") or config.get("code") or ""
        self.access_code = str(raw_code).strip() if isinstance(raw_code, (str, int, float)) else ""
        self.serial_number = str(config.get("serialNumber") or config.get("serial") or "")
        self.spool_db_file = config.get("spoolDbFile", f"./spool_{self.id}.json")
        self.filament_grams = float(config.get("filament_grams", 1000.0))
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

        # Per-slot AMS filament weight tracking (Keys: "0"=A1, "1"=A2, "2"=A3, "3"=A4, "255"=External)
        raw_ams_slots = config.get("ams_slots") or {}
        default_slots = {
            AMSSlot.A1.value: 1000.0,
            AMSSlot.A2.value: 1000.0,
            AMSSlot.A3.value: 1000.0,
            AMSSlot.A4.value: 1000.0,
            AMSSlot.EXTERNAL.value: 1000.0,
        }
        self.ams_slots: dict[str, float] = {k: float(v) for k, v in {**default_slots, **raw_ams_slots}.items()}

        self.storage = storage
        self.save_callback = save_callback
        self._client: mqtt.Client | None = None
        self._is_printing = False
        self._was_running = False
        self._job_started_from_app = False
        self._history_recorded = False
        self._current_job_grams = 0.0
        self._job_deducted = False
        self._is_calibrating = False
        self.last_job_grams = 0.0
        self.current_job_objects: list[dict[str, Any]] = []
        self.skipped_objects: list[int] = []
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
        self.ams_humidity_idx: int = 1
        self.ams_temp: float = 0.0
        self.active_ams_tray: int = 255
        self.ams_exist_bits: str = str(config.get("ams_exist_bits", "0"))
        raw_ams_enabled = config.get("ams_enabled")
        self.ams_enabled: bool | None = bool(raw_ams_enabled) if raw_ams_enabled is not None else None
        self.ams_trays_info: dict[str, dict] = {}

    @property
    def has_ams(self) -> bool:
        """Returns True if printer has at least 1 active AMS unit connected with valid trays."""
        if self.ams_enabled is False:
            return False
        if self.ams_enabled is True:
            return True

        exist_bits = str(getattr(self, "ams_exist_bits", ""))
        if exist_bits in ["0", "0000"]:
            return False

        if not self.ams_units or not isinstance(self.ams_units, list):
            return False

        total_trays = 0
        for unit in self.ams_units:
            if isinstance(unit, dict):
                trays = unit.get("tray", [])
                if isinstance(trays, list):
                    for t in trays:
                        if isinstance(t, dict) and (t.get("tray_type") or t.get("id") is not None):
                            total_trays += 1

        return total_trays > 0

    def get_active_slot_key(self) -> str:
        s_key = str(self.active_ams_tray)
        if s_key in self.ams_slots:
            return s_key
        return AMSSlot.EXTERNAL.value if AMSSlot.A1.value in self.ams_slots else AMSSlot.EXTERNAL.value

    def get_slot_grams(self, slot_id: Any | None = None) -> float:
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        return float(self.ams_slots.get(s_key, self.filament_grams))

    def set_slot_grams(self, grams: float, slot_id: Any | None = None) -> None:
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        g_val = round(float(grams), 2)
        self.ams_slots[s_key] = g_val
        if s_key == self.get_active_slot_key():
            self.filament_grams = g_val

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
        self._client.on_error = self._on_error  # type: ignore[attr-defined]

        try:
            self._client.connect_async(self.ip, 8883, 60)
            self._client.loop_start()
            logger.info(f"🚀 Initialized MQTT client for [{self.name}] ({self.ip})")
        except Exception as e:
            logger.error(f"❌ Failed connecting MQTT for [{self.name}]: {e}")

    def destroy(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info(f"🛑 Disconnected MQTT for [{self.name}]")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            logger.info(f"✅ Connected to Bambu MQTT [{self.name}] ({self.ip})")
            if self.serial_number:
                client.subscribe(f"device/{self.serial_number}/report")
                push_req = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}})
                client.publish(f"device/{self.serial_number}/request", push_req)
        else:
            self.is_mqtt_connected = False
            logger.error(f"❌ MQTT connection error [{self.name}] code: {rc}")

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        self.is_mqtt_connected = False
        logger.warning(f"⚠️ MQTT disconnected for [{self.name}] (code: {rc})")

    def _on_error(self, client: Any, userdata: Any, rc: Any) -> None:
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
        if self._ftps_fetching or not self.ip or not self.access_code:
            return
        self._ftps_fetching = True

        def _worker() -> None:
            try:
                if self.ip and self.access_code:
                    from services.ftps_client import fetch_bambu_ftps_info
                    info = fetch_bambu_ftps_info(self.ip, self.access_code, self.subtask_name)
                    w = float(info.get("weight_g") or 0.0)
                    objs = info.get("objects") or []
                    if objs:
                        self.current_job_objects = objs
                        logger.info(f"🧩 FTPS fetched {len(objs)} objects for [{self.name}]: {[o['name'] for o in objs]}")
                    if w > 0:
                        self._current_job_grams = w
                        logger.info(f"💡 FTPS fetched model weight {w}g for [{self.name}]")
                        if self.gcode_state == "RUNNING" and not self._job_deducted:
                            active_key = self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            new_w = round(old_w - self._current_job_grams, 2)
                            self.set_slot_grams(new_w, active_key)
                            self._job_deducted = True
                            self.last_job_grams = self._current_job_grams
                            logger.info(
                                f"💾 Auto-deducted {self._current_job_grams}g (via FTPS) from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g"
                            )
                            self._trigger_save()
            except Exception as e:
                logger.warning(f"FTPS worker error for [{self.name}]: {e}")
            finally:
                self._ftps_fetching = False

        loop_to_use = self._get_active_event_loop()
        if loop_to_use:
            asyncio.run_coroutine_threadsafe(asyncio.to_thread(_worker), loop_to_use)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        try:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            parsed = parse_mqtt_payload(msg.payload)
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
                self.skipped_objects = parsed["skipped_objects"]

            if "ams_exist_bits" in parsed:
                self.ams_exist_bits = parsed["ams_exist_bits"]
            if "active_ams_tray" in parsed:
                self.active_ams_tray = parsed["active_ams_tray"]
            if "ams_units" in parsed:
                self.ams_units = parsed["ams_units"]
            if "ams_trays_info" in parsed:
                self.ams_trays_info.update(parsed["ams_trays_info"])
            if "ams_humidity_idx" in parsed:
                self.ams_humidity_idx = parsed["ams_humidity_idx"]
            if "ams_temp" in parsed:
                self.ams_temp = parsed["ams_temp"]

            if "vt_tray_info" in parsed:
                self.ams_trays_info["255"] = parsed["vt_tray_info"]

            filament = print_data.get("vt_tray", {}).get("tray_type")
            if not filament and self.ams_units:
                for ams_b in self.ams_units:
                    for tray in ams_b.get("tray", []):
                        if str(tray.get("id")) == str(self.active_ams_tray) and tray.get("tray_type"):
                            filament = tray.get("tray_type")
                            break
            if filament:
                self.filament_type = filament

            # Subtask change & calibration tracking
            curr_subtask = str(self.subtask_name or "").strip()
            is_calib_name = any(k in curr_subtask.lower() for k in ["calib", "g32", "calibration"])
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

            # Extract model weight
            w_val = extract_model_weight(print_data)
            if w_val > 0 and self._current_job_grams == 0.0:
                self._current_job_grams = w_val

            # Check OrcaSlicer cache file if weight is still 0.0 (strictly verify filename match or recent slice timestamp)
            if self._current_job_grams == 0.0:
                cache_file = STORAGE_DIR / "last_sliced_weight.json"
                if cache_file.exists():
                    try:
                        c_data = json.loads(cache_file.read_text(encoding="utf-8"))
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

            # Check subtask filename regex if weight is still 0.0
            if self._current_job_grams == 0.0 and self.subtask_name:
                w_fname = extract_subtask_weight(self.subtask_name)
                if w_fname > 0:
                    self._current_job_grams = w_fname
                    logger.info(f"💡 Extracted weight {w_fname}g from subtask_name for [{self.name}]")

            # Trigger FTPS fetch to download 3MF/gcode from printer SD card and extract exact weight/objects from slice_info.config / .gcode
            if self.gcode_state in ["RUNNING", "PAUSE"] and (self._current_job_grams == 0.0 or not self.current_job_objects):
                now_ts = time.time()
                if (
                    not self._ftps_fetching
                    and getattr(self, "_ftps_attempts", 0) < 5
                    and (now_ts - getattr(self, "_last_ftps_time", 0.0) >= 8.0)
                ):
                    self._ftps_attempts = getattr(self, "_ftps_attempts", 0) + 1
                    self._last_ftps_time = now_ts
                    self._try_ftps_fetch()

            if self.gcode_state in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PAUSE"]:
                if not getattr(self, "_is_calibrating", False) and self._current_job_grams > 0 and not self._job_deducted:
                    active_key = self.get_active_slot_key()
                    old_w = self.get_slot_grams(active_key)
                    new_w = max(0.0, round(old_w - self._current_job_grams, 2))
                    self.set_slot_grams(new_w, active_key)
                    self._job_deducted = True
                    self.last_job_grams = self._current_job_grams
                    logger.info(
                        f"💾 Auto-deducted {self._current_job_grams}g from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g"
                    )
                    self._trigger_save()

            elif self.gcode_state in ["FINISH", "IDLE", "FAILED"]:
                if getattr(self, "_is_calibrating", False):
                    self._job_deducted = True
                    self._current_job_grams = 0.0
                    self._is_calibrating = False
                was_active = (
                    self._is_printing
                    or getattr(self, "_was_running", False)
                    or getattr(self, "_job_started_from_app", False)
                )
                should_record_history = was_active and not getattr(self, "_history_recorded", False)

                if self.gcode_state == "FINISH" or should_record_history:
                    if not self._job_deducted:
                        if self._current_job_grams == 0.0:
                            cache_file = STORAGE_DIR / "last_sliced_weight.json"
                            if cache_file.exists():
                                try:
                                    c_data = json.loads(cache_file.read_text(encoding="utf-8"))
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
                                    w_fname = float(m_fname.group(1).replace(",", "."))
                                    if 0 < w_fname < 5000:
                                        self._current_job_grams = w_fname
                                except ValueError:
                                    pass

                        deduct_w = self._current_job_grams
                        if deduct_w > 0:
                            active_key = self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            new_w = max(0.0, round(old_w - deduct_w, 2))
                            self.set_slot_grams(new_w, active_key)
                            self._job_deducted = True
                            self.last_job_grams = deduct_w
                            logger.info(
                                f"💾 Auto-deducted {deduct_w}g on FINISH from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g"
                            )
                            self._trigger_save()

                    if self.finish_timestamp == 0.0:
                        self.finish_timestamp = time.time()

                    if should_record_history:
                        logger.info(f"🎉 Print finished/completed on [{self.name}] (state: {self.gcode_state})!")
                        final_weight = self._current_job_grams or getattr(self, "last_job_grams", 0.0) or 0.0
                        if final_weight == 0.0 and self.subtask_name:
                            final_weight = extract_subtask_weight(self.subtask_name)

                        if final_weight == 0.0:
                            cache_file = STORAGE_DIR / "last_sliced_weight.json"
                            if cache_file.exists():
                                try:
                                    c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                                    c_w = float(c_data.get("weight", 0.0))
                                    if c_w > 0:
                                        final_weight = c_w
                                except Exception:
                                    pass

                        note_text = "Успішно виконано" if self.gcode_state == "FINISH" else "Завершено"

                        raw_title = getattr(self, "_custom_job_name", None) or str(self.subtask_name or "").strip()
                        raw_title = raw_title.replace("Metadata/", "").replace("metadata/", "").strip()
                        if "." in raw_title and not raw_title.endswith((".3mf", ".gcode")):
                            raw_title = raw_title.rsplit(".", 1)[0]
                        elif raw_title.endswith((".3mf", ".gcode")):
                            raw_title = raw_title.rsplit(".", 1)[0]

                        clean_subtask = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_title).strip()
                        if not clean_subtask or clean_subtask.lower() in ["untitled", "none", "null"] or re.match(r"^[_ -]+$", clean_subtask):
                            clean_subtask = "Деталь 3D"

                        entry = {
                            "timestamp": time.time(),
                            "printer_name": self.name,
                            "subtask_name": clean_subtask,
                            "weight_g": round(float(final_weight), 1),
                            "filament_type": self.filament_type,
                            "note": note_text,
                        }
                        if self.storage:
                            loop_to_use = self._get_active_event_loop()
                            if loop_to_use:
                                asyncio.run_coroutine_threadsafe(self.storage.add_history_entry(entry), loop_to_use)
                            else:
                                logger.warning(f"⚠️ Event loop unresolvable for history entry on [{self.name}]")
                        self._history_recorded = True
                        self._is_printing = False
                        self._was_running = False
                        self._job_started_from_app = False

                    self._is_printing = False

                if self.gcode_state in ["IDLE", "FAILED", "FINISH", "SUCCESS", "CANCEL"]:
                    # Reset state counters & job objects for next job
                    self.finish_timestamp = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self.finish_timestamp
                    self.job_start_time = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self.job_start_time
                    self.current_job_objects = []
                    self.skipped_objects = []
                    self._is_printing = False
                    self._was_running = False
                    self._job_started_from_app = False
                    self._job_deducted = False if self.gcode_state in ["IDLE", "FAILED"] else self._job_deducted
                    self._ftps_attempted = False
                    self._ftps_attempts = 0
                    self._last_ftps_time = 0.0
                    self._current_job_grams = 0.0 if self.gcode_state in ["IDLE", "FAILED"] else self._current_job_grams
                    self._history_recorded = False if self.gcode_state in ["IDLE", "FAILED"] else self._history_recorded

        except Exception as e:
            logger.error(f"Error processing MQTT message for [{self.name}]: {e}")

    def pause(self) -> bool:
        if not self._client or not self._client.is_connected():
            return False
        payload = json.dumps({"print": {"sequence_id": str(int(time.time())), "command": "pause"}})
        self._client.publish(f"device/{self.serial_number}/request", payload)
        return True

    def pause_print(self) -> bool:
        return self.pause()

    def resume(self) -> bool:
        if not self._client or not self._client.is_connected():
            return False
        payload = json.dumps({"print": {"sequence_id": str(int(time.time())), "command": "resume"}})
        self._client.publish(f"device/{self.serial_number}/request", payload)
        return True

    def resume_print(self) -> bool:
        return self.resume()

    def stop_print(self) -> bool:
        if not self._client or not self._client.is_connected():
            return False
        payload = json.dumps({"print": {"sequence_id": str(int(time.time())), "command": "stop"}})
        self._client.publish(f"device/{self.serial_number}/request", payload)
        return True

    def set_speed_level(self, level: int) -> bool:
        """Sets speed level: 1 = Silent (50%), 2 = Standard (100%), 3 = Sport (124%), 4 = Ludicrous (166%)."""
        if not self._client or not self._client.is_connected():
            return False
        param_str = str(max(1, min(4, level)))
        payload = json.dumps(
            {"print": {"sequence_id": str(int(time.time())), "command": "print_speed", "param": param_str}}
        )
        self._client.publish(f"device/{self.serial_number}/request", payload)
        self.spd_lvl = level
        return True

    def set_print_speed(self, level: int) -> bool:
        return self.set_speed_level(level)

    def toggle_chamber_light(self, mode: str = "toggle") -> bool:
        """Toggles or sets chamber LED light ('on', 'off', 'toggle')."""
        if not self._client or not self._client.is_connected():
            return False
        new_mode = "off" if self.chamber_light_state == "on" else "on" if mode == "toggle" else mode
        payload = json.dumps(
            {
                "system": {
                    "sequence_id": str(int(time.time())),
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": new_mode,
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "loop_times": 0,
                    "interval_time": 0,
                }
            }
        )
        self._client.publish(f"device/{self.serial_number}/request", payload)
        self.chamber_light_state = new_mode
        return True

    def set_chamber_light(self, mode: str = "toggle") -> bool:
        return self.toggle_chamber_light(mode)

    def start_calibration(self) -> bool:
        """
        Triggers full automatic Bambu Lab calibration (vibration frequency calibration + auto bed leveling).
        Publishes MQTT calibration command and G32 gcode line.
        """
        if not self._client or not self._client.is_connected():
            return False

        self._is_calibrating = True
        self._job_deducted = True
        self._current_job_grams = 0.0

        # 1. Native Bambu Lab calibration command (Option 63 = Full Calibration)
        payload_cal = json.dumps(
            {"print": {"sequence_id": str(int(time.time())), "command": "calibration", "option": 63}}
        )
        self._client.publish(f"device/{self.serial_number}/request", payload_cal)

        # 2. Backup G32 gcode_line command for compatibility across firmware versions
        payload_g32 = json.dumps(
            {"print": {"sequence_id": str(int(time.time()) + 1), "command": "gcode_line", "param": "G32\n"}}
        )
        self._client.publish(f"device/{self.serial_number}/request", payload_g32)
        logger.info(f"🎯 Triggered automatic calibration (G32 / option 63) for [{self.name}] ({self.serial_number})")
        return True

    async def skip_objects_async(self, obj_ids: list[int]) -> tuple[bool, str]:
        """
        Sends MQTT print.skip_objects command to skip specific object IDs on the current plate.
        Does not stop the print job.
        """
        if not self._client or not self._client.is_connected():
            return False, "Принтер не підключений по MQTT"
        if not obj_ids or not isinstance(obj_ids, list):
            return False, "Необхідно вказати список ID об'єктів для пропуску"

        int_obj_ids = [int(i) for i in obj_ids if str(i).isdigit()]
        if not int_obj_ids:
            return False, "Список ID об'єктів порожній або некоректний"

        payload = {
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "skip_objects",
                "obj_list": int_obj_ids,
            }
        }
        topic = f"device/{self.serial_number}/request"
        result = self._client.publish(topic, json.dumps(payload), qos=1)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            return False, "Не вдалося відправити MQTT команду пропуску об'єктів"

        for oid in int_obj_ids:
            if oid not in self.skipped_objects:
                self.skipped_objects.append(oid)

        logger.info(f"🚫 Sent skip_objects {int_obj_ids} to printer [{self.name}] ({self.serial_number})")
        return True, f"Об'єкт(и) {int_obj_ids} успішно пропущено"

    async def start_print_job_async(
        self, file_bytes: bytes, filename: str, plate_name: str = "plate_1.gcode", use_ams: bool = True, part_name: str | None = None
    ) -> tuple[bool, str]:
        """
        Uploads 3MF file via FTPS to printer SD card and publishes MQTT project_file command to start printing.
        Returns (success: bool, user_message: str).
        """
        import re

        if not self._client or not self._client.is_connected():
            return False, "⚠️ MQTT з'єднання з принтером відсутнє."

        # 1. Upload 3MF file to SD card via FTPS
        remote_path = await asyncio.to_thread(upload_3mf_to_bambu, self.ip, self.access_code, file_bytes, filename)
        if not remote_path:
            return False, f"⚠️ Не вдалося завантажити файл по FTPS на {self.name} (перевірте IP {self.ip} та SD-карту)."

        # Verify file size on printer MicroSD card via FTPS SIZE command instead of blind sleep
        expected_size = len(file_bytes)
        verified = await asyncio.to_thread(verify_bambu_file_size, self.ip, self.access_code, remote_path, expected_size)
        if not verified:
            logger.warning(f"⚠️ SD card size verification unconfirmed for {remote_path} on [{self.name}]. Proceeding with job dispatch...")

        # 2. Prepare MQTT project_file command with correct file:///sdcard/ URL path and MD5 hash
        clean_file = remote_path.split("/")[-1]
        if remote_path.startswith("file:///sdcard/"):
            url_path = remote_path
        elif remote_path.startswith("sdcard/"):
            url_path = f"file:///{remote_path}"
        elif remote_path.startswith("/"):
            url_path = f"file:///sdcard{remote_path}"
        else:
            url_path = f"file:///sdcard/{remote_path}"

        # Dynamically verify sub_path inside 3MF container
        sub_path = "Metadata/plate_1.gcode"
        if zipfile.is_zipfile(io.BytesIO(file_bytes)):
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    names = zf.namelist()
                    if plate_name and f"Metadata/{plate_name}" in names:
                        sub_path = f"Metadata/{plate_name}"
                    elif plate_name and plate_name.startswith("Metadata/") and plate_name in names:
                        sub_path = plate_name
                    elif plate_name and plate_name in names:
                        sub_path = f"Metadata/{plate_name}" if not plate_name.startswith("Metadata/") else plate_name
                    elif "Metadata/plate_1.gcode" in names:
                        sub_path = "Metadata/plate_1.gcode"
                    elif "Metadata/slice_info.config" in names:
                        sub_path = "Metadata/slice_info.config"
                    else:
                        gc_meta = [n for n in names if n.startswith("Metadata/") and n.endswith(".gcode")]
                        if gc_meta:
                            sub_path = gc_meta[0]
            except Exception as e_zip:
                logger.warning(f"Failed zip sub_path scan for {filename}: {e_zip}")

        # Always guarantee Metadata/ prefix for Bambu Lab firmware path resolution
        if not sub_path.startswith("Metadata/"):
            sub_path = f"Metadata/{sub_path}"

        md5_str = hashlib.md5(file_bytes).hexdigest()

        # Preserve human-readable Unicode/Cyrillic part name or filename
        display_title = part_name or filename
        if "." in display_title:
            display_title = display_title.rsplit(".", 1)[0]

        clean_subtask = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", display_title).strip()
        if not clean_subtask or re.match(r"^[_ -]+$", clean_subtask):
            clean_subtask = "Деталь 3D"

        self.subtask_name = clean_subtask
        self._custom_job_name = clean_subtask

        # Pre-calculate filament weight & extract plate objects from uploaded 3MF file
        try:
            m_info = parse_3mf_file(file_bytes, filename)
            self.current_job_objects = m_info.get("objects", [])
            self.skipped_objects = []
            w_g = float(m_info.get("weight_g") or 0.0)

            # Persist objects & weight into last_sliced_weight.json cache
            try:
                cache_file = STORAGE_DIR / "last_sliced_weight.json"
                cache_payload = {
                    "filename": filename,
                    "weight": w_g,
                    "timestamp": time.time(),
                    "objects": self.current_job_objects,
                }
                cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")
                logger.info(f"🧩 Persisted {len(self.current_job_objects)} objects to weight cache for [{self.name}]")
            except Exception as e_cache:
                logger.warning(f"Failed writing weight/objects cache: {e_cache}")

            if w_g > 0:
                self._current_job_grams = w_g
                self._job_deducted = False
                logger.info(f"⚖️ Parsed 3MF weight {w_g}g for [{self.name}]")

                # Deduct immediately from active slot
                active_key = self.get_active_slot_key()
                old_w = self.get_slot_grams(active_key)
                new_w = max(0.0, round(old_w - w_g, 2))
                self.set_slot_grams(new_w, active_key)
                self._job_deducted = True
                self.last_job_grams = w_g
                logger.info(
                    f"💾 Auto-deducted {w_g}g from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g"
                )
                self._trigger_save()
        except Exception as e_w:
            logger.warning(f"Could not parse 3MF weight in start_print_job_async: {e_w}")

        timestamp_id = str(int(time.time()))
        has_ams_hardware = bool(getattr(self, "has_ams", False))
        active_slot = str(self.get_active_slot_key())

        use_ams_bool = bool(use_ams and has_ams_hardware)
        ams_mapping_list: list[int] = []

        if use_ams_bool:
            if active_slot.isdigit():
                ams_mapping_list = [int(active_slot)]
            elif active_slot == "255":
                ams_mapping_list = [255]
            else:
                ams_mapping_list = [0]
        else:
            use_ams_bool = False
            ams_mapping_list = []

        payload = {
            "print": {
                "sequence_id": timestamp_id,
                "command": "project_file",
                "param": sub_path,
                "project_id": timestamp_id,
                "profile_id": timestamp_id,
                "task_id": timestamp_id,
                "subtask_id": timestamp_id,
                "subtask_name": clean_subtask,
                "url": url_path,
                "file": remote_path,
                "md5": md5_str,
                "timelapse": False,
                "bed_type": "auto",
                "bed_levelling": True,
                "flow_cali": True,
                "vibration_cali": True,
                "layer_inspect": True,
                "use_ams": use_ams_bool,
                "ams_mapping": ams_mapping_list,
            }
        }

        try:
            self._client.publish(f"device/{self.serial_number}/request", json.dumps(payload))
            logger.info(
                f"🚀 Sent MQTT project_file command for {clean_file} (url: {url_path}, md5: {md5_str}) to [{self.name}]"
            )
            return (
                True,
                f"✅ Файл <code>{html.escape(filename)}</code> успішно відправлено по FTPS та запущено на друк на <b>{html.escape(self.name)}</b>!",
            )
        except Exception as e:
            logger.error(f"Error publishing MQTT project_file for [{self.name}]: {e}")
            return False, f"⚠️ Помилка відправки MQTT команди на друк: {e}"

    def calculate_job_cost(self, weight_grams: float, print_mins: int = 0) -> dict[str, float]:
        """Calculates cost breakdown: filament cost + electricity cost in UAH."""
        if weight_grams <= 0:
            return {"filament_cost": 0.0, "electricity_cost": 0.0, "total_cost": 0.0}

        filament_cost = (weight_grams / 1000.0) * self.price_per_kg
        effective_mins = print_mins if print_mins > 0 else max(10, int(weight_grams * 2.0))
        electricity_kwh = (self.power_watts / 1000.0) * (effective_mins / 60.0)
        electricity_cost = electricity_kwh * self.electricity_rate_uah

        return {
            "filament_cost": round(filament_cost, 2),
            "electricity_cost": round(electricity_cost, 2),
            "total_cost": round(filament_cost + electricity_cost, 2),
        }

    def record_print_hours(self, hours: float) -> None:
        """Records completed print hours towards total and maintenance counters."""
        if hours <= 0:
            return
        self.total_print_hours = round(self.total_print_hours + hours, 2)
        self.maintenance_hours_counter = round(self.maintenance_hours_counter + hours, 2)
        for k, item in self.maintenance_items.items():
            item["counter_hours"] = round(item.get("counter_hours", 0.0) + hours, 2)
        logger.info(f"⏱️ Updated print hours for [{self.name}]: +{hours:.2f}h (Total: {self.total_print_hours:.1f}h)")
        self._trigger_save()

    def reset_maintenance_counter(self, item_key: str = "rails") -> None:
        """Resets a specific maintenance item's counter after servicing."""
        now_ts = time.time()
        if item_key == "all":
            self.maintenance_hours_counter = 0.0
            self.last_maintenance_timestamp = now_ts
            for item in self.maintenance_items.values():
                item["counter_hours"] = 0.0
                item["last_reset"] = now_ts
        elif item_key in self.maintenance_items:
            self.maintenance_items[item_key]["counter_hours"] = 0.0
            self.maintenance_items[item_key]["last_reset"] = now_ts
            if item_key == "rails":
                self.maintenance_hours_counter = 0.0
                self.last_maintenance_timestamp = now_ts
        else:
            self.maintenance_hours_counter = 0.0
            self.last_maintenance_timestamp = now_ts

        logger.info(f"🧹 Maintenance counter ({item_key}) reset for [{self.name}]")
        self._trigger_save()

    def set_maintenance_interval(self, item_key: str, interval_hours: float) -> None:
        """Sets target maintenance interval in hours for a specific item."""
        val = max(1.0, float(interval_hours))
        if item_key in self.maintenance_items:
            self.maintenance_items[item_key]["interval_hours"] = val
        if item_key == "rails":
            self.maintenance_interval_hours = int(val)
        logger.info(f"⚙️ Maintenance interval for [{self.name}] ({item_key}) set to {val}h")
        self._trigger_save()

    @property
    def mapped_state(self) -> str:
        """Maps internal gcode_state into 3 canonical user-facing states: RUNNING, PAUSE, IDLE."""
        st = str(self.gcode_state or "IDLE").upper()
        if st in ["RUNNING", "PREPARING", "PREPARATION", "BUILDING", "PRINTING", "SLICING", "BUSY", "CHANGING_FILAMENT", "MAM_CLEANING"]:
            return "RUNNING"
        if st in ["PAUSE", "PAUSED"]:
            return "PAUSE"
        return "IDLE"

    def to_dict(self, for_storage: bool = False) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "accessCode": self.access_code if for_storage else ("••••••••" if self.access_code else ""),
            "serialNumber": self.serial_number,
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
            "hms_errors": self.hms_errors,
            "hms_resolved": self.hms_resolved,
            "chamber_light_state": self.chamber_light_state,
        }

    def to_storage_dict(self) -> dict[str, Any]:
        """Returns unmasked dictionary representation for internal SQLite / JSON storage persistence."""
        return self.to_dict(for_storage=True)
