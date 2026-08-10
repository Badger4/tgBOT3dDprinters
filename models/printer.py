"""
Bambu Lab 3D Printer MQTT client and domain model.
"""
import io
import ssl
import html
import json
import uuid
import time
import zipfile
import hashlib
import asyncio
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt
from config import logger, STORAGE_DIR
from services.ftps_client import extract_model_weight, fetch_bambu_ftps_weight, upload_3mf_to_bambu
from storage.manager import StorageManager
from models.enums import AMSSlot, GCodeState

DEFAULT_MAINTENANCE_ITEMS = {
    "rails": {
        "key": "rails",
        "name": "Змащення валів & направляючих",
        "counter_hours": 0.0,
        "interval_hours": 100.0,
        "last_reset": 0.0
    },
    "nozzle": {
        "key": "nozzle",
        "name": "Чистка сопла & екструдера",
        "counter_hours": 0.0,
        "interval_hours": 50.0,
        "last_reset": 0.0
    },
    "belts": {
        "key": "belts",
        "name": "Перевірка натягу ременів",
        "counter_hours": 0.0,
        "interval_hours": 150.0,
        "last_reset": 0.0
    },
    "filter": {
        "key": "filter",
        "name": "Заміна вугільного фільтра",
        "counter_hours": 0.0,
        "interval_hours": 300.0,
        "last_reset": 0.0
    }
}

class BambuPrinter:
    """Manages Bambu Lab 3D Printer telemetry and MQTT control."""
    def __init__(self, config: Dict[str, Any], storage: StorageManager, save_callback: Optional[Any] = None):
        self.id = str(config.get("id") or uuid.uuid4())
        self.name = config.get("name", "Bambu Printer")
        self.ip = config.get("ip", "")
        self.access_code = str(config.get("accessCode") or config.get("code") or "")
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
        self.maintenance_items: Dict[str, Dict[str, Any]] = {}
        for k, def_item in DEFAULT_MAINTENANCE_ITEMS.items():
            user_item = raw_maint_items.get(k, {})
            c_hrs = float(user_item.get("counter_hours", self.maintenance_hours_counter if k == "rails" else 0.0))
            i_hrs = float(user_item.get("interval_hours", self.maintenance_interval_hours if k == "rails" else def_item["interval_hours"]))
            self.maintenance_items[k] = {
                "key": k,
                "name": def_item["name"],
                "counter_hours": c_hrs,
                "interval_hours": i_hrs,
                "last_reset": float(user_item.get("last_reset", 0.0))
            }

        # Per-slot AMS filament weight tracking (Keys: "0"=A1, "1"=A2, "2"=A3, "3"=A4, "255"=External)
        raw_ams_slots = config.get("ams_slots") or {}
        default_slots = {
            AMSSlot.A1.value: 1000.0,
            AMSSlot.A2.value: 1000.0,
            AMSSlot.A3.value: 1000.0,
            AMSSlot.A4.value: 1000.0,
            AMSSlot.EXTERNAL.value: 1000.0
        }
        self.ams_slots: Dict[str, float] = {k: float(v) for k, v in {**default_slots, **raw_ams_slots}.items()}

        self.storage = storage
        self.save_callback = save_callback
        self._client: Optional[mqtt.Client] = None
        self._is_printing = False
        self._current_job_grams = 0.0
        self._job_deducted = False
        self.last_job_grams = 0.0
        self._ftps_fetching = False
        self._ftps_attempted = False
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

        # Live telemetry
        self.gcode_state = config.get("gcode_state", "IDLE")
        self.nozzle_temper = int(config.get("nozzle_temper", 0))
        self.bed_temper = int(config.get("bed_temper", 0))
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
        self.finish_timestamp: float = 0.0
        self.ams_units: list = []
        self.ams_humidity_idx: int = 1
        self.active_ams_tray: int = 255

    @property
    def has_ams(self) -> bool:
        """Returns True if printer has at least 1 active AMS unit connected."""
        return bool(self.ams_units and len(self.ams_units) > 0)

    def get_active_slot_key(self) -> str:
        s_key = str(self.active_ams_tray)
        if s_key in self.ams_slots:
            return s_key
        return AMSSlot.EXTERNAL.value if AMSSlot.A1.value in self.ams_slots else AMSSlot.EXTERNAL.value

    def get_slot_grams(self, slot_id: Optional[Any] = None) -> float:
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        return float(self.ams_slots.get(s_key, self.filament_grams))

    def set_slot_grams(self, grams: float, slot_id: Optional[Any] = None):
        s_key = str(slot_id) if slot_id is not None else self.get_active_slot_key()
        g_val = round(float(grams), 2)
        self.ams_slots[s_key] = g_val
        if s_key == self.get_active_slot_key():
            self.filament_grams = g_val

    def init_mqtt(self):
        if not self.ip or not self.serial_number:
            logger.warning(f"[{self.name}] Missing IP or Serial, MQTT disabled.")
            return

        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None

        self._client = mqtt.Client(client_id=f"BambuBot_{self.id[:10]}")
        self._client.username_pw_set("bblp", self.access_code)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self._client.tls_set_context(context)

        self.is_mqtt_connected = False
        self.last_mqtt_msg_time = time.time()

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_error = self._on_error

        try:
            self._client.connect_async(self.ip, 8883, 60)
            self._client.loop_start()
            logger.info(f"🚀 Initialized MQTT client for [{self.name}] ({self.ip})")
        except Exception as e:
            logger.error(f"❌ Failed connecting MQTT for [{self.name}]: {e}")

    def destroy(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info(f"🛑 Disconnected MQTT for [{self.name}]")

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            logger.info(f"✅ Connected to Bambu MQTT [{self.name}]")
            client.subscribe(f"device/{self.serial_number}/report")
            push_req = json.dumps({"pushing": {"sequence_id": "0", "command": "pushall"}})
            client.publish(f"device/{self.serial_number}/request", push_req)
        else:
            self.is_mqtt_connected = False
            logger.error(f"❌ MQTT connection error [{self.name}] code: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.is_mqtt_connected = False
        logger.warning(f"⚠️ MQTT disconnected for [{self.name}] (code: {rc})")

    def _on_error(self, client, userdata, rc):
        logger.error(f"❌ MQTT error [{self.name}]: {rc}")

    def _trigger_save(self):
        if self.save_callback:
            try:
                if self._main_loop and self._main_loop.is_running():
                    if asyncio.iscoroutinefunction(self.save_callback):
                        asyncio.run_coroutine_threadsafe(self.save_callback(), self._main_loop)
                    else:
                        self._main_loop.call_soon_threadsafe(self.save_callback)
            except Exception as e:
                logger.warning(f"Failed triggering save callback for [{self.name}]: {e}")

    def _try_ftps_fetch(self):
        if self._ftps_fetching or not self.ip or not self.access_code:
            return
        self._ftps_fetching = True

        def _worker():
            try:
                w = fetch_bambu_ftps_weight(self.ip, self.access_code, self.subtask_name)
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
                        logger.info(f"💾 Auto-deducted {self._current_job_grams}g (via FTPS) from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g")
                        self._trigger_save()
            except Exception as e:
                logger.warning(f"FTPS worker error for [{self.name}]: {e}")
            finally:
                self._ftps_fetching = False

        if self._main_loop and self._main_loop.is_running():
            asyncio.run_coroutine_threadsafe(asyncio.to_thread(_worker), self._main_loop)

    def _on_message(self, client, userdata, msg):
        try:
            self.is_mqtt_connected = True
            self.last_mqtt_msg_time = time.time()
            payload = json.loads(msg.payload.decode('utf-8'))
            print_data = payload.get("print")
            if not print_data:
                return

            if "gcode_state" in print_data:
                self.gcode_state = print_data["gcode_state"]
            if "nozzle_temper" in print_data:
                self.nozzle_temper = round(print_data["nozzle_temper"])
            if "bed_temper" in print_data:
                self.bed_temper = round(print_data["bed_temper"])
            if "mc_percent" in print_data:
                self.mc_percent = print_data["mc_percent"]
            if "mc_remaining_time" in print_data:
                self.mc_remaining_time = print_data["mc_remaining_time"]
            if "layer_num" in print_data:
                self.layer_num = print_data["layer_num"]
            if "total_layer_num" in print_data:
                self.total_layer_num = print_data["total_layer_num"]
            if "subtask_name" in print_data:
                self.subtask_name = print_data["subtask_name"]
            if "spd_lvl" in print_data:
                self.spd_lvl = print_data["spd_lvl"]
            if "spd_mag" in print_data:
                self.spd_mag = print_data["spd_mag"]

            if "lights_report" in print_data and isinstance(print_data["lights_report"], list):
                for light in print_data["lights_report"]:
                    if light.get("node") == "chamber_light":
                        self.chamber_light_state = light.get("mode", "off")

            if "hms" in print_data and isinstance(print_data["hms"], list):
                self.hms_errors = print_data["hms"]

            if "ams" in print_data and isinstance(print_data["ams"], dict):
                ams_info = print_data["ams"]
                if "tray_now" in ams_info:
                    try:
                        self.active_ams_tray = int(ams_info["tray_now"])
                    except (ValueError, TypeError):
                        self.active_ams_tray = 255

                if "ams" in ams_info and isinstance(ams_info["ams"], list):
                    self.ams_units = ams_info["ams"]
                    if self.ams_units:
                        unit = self.ams_units[0]
                        if "humidity" in unit:
                            try:
                                self.ams_humidity_idx = int(unit["humidity"])
                            except (ValueError, TypeError):
                                pass
                        if "temp" in unit:
                            try:
                                self.ams_temp = float(unit["temp"])
                            except (ValueError, TypeError):
                                pass

            filament = print_data.get("vt_tray", {}).get("tray_type")
            if not filament and self.ams_units:
                for ams_b in self.ams_units:
                    for tray in ams_b.get("tray", []):
                        if str(tray.get("id")) == str(self.active_ams_tray) and tray.get("tray_type"):
                            filament = tray.get("tray_type")
                            break
            if filament:
                self.filament_type = filament

            # Extract model weight
            w_val = extract_model_weight(print_data)
            if w_val > 0 and self._current_job_grams == 0.0:
                self._current_job_grams = w_val

            # ALWAYS trigger FTPS fetch to download 3MF from SD card and extract exact weight from slice_info.config / .gcode
            if self.gcode_state in ["RUNNING", "PAUSE"] and not self._ftps_fetching and not self._ftps_attempted:
                self._ftps_attempted = True
                self._try_ftps_fetch()

            if self.gcode_state == "RUNNING":
                if not self._is_printing:
                    self._is_printing = True

                if self._current_job_grams > 0 and not self._job_deducted:
                    active_key = self.get_active_slot_key()
                    old_w = self.get_slot_grams(active_key)
                    new_w = round(old_w - self._current_job_grams, 2)
                    self.set_slot_grams(new_w, active_key)
                    self._job_deducted = True
                    self.last_job_grams = self._current_job_grams
                    logger.info(f"💾 Auto-deducted {self._current_job_grams}g from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g")
                    self._trigger_save()

            elif self.gcode_state in ["FINISH", "IDLE", "FAILED"]:
                if self.gcode_state == "FINISH" and self._is_printing:
                    logger.info(f"🎉 Print finished on [{self.name}]!")
                    if not self._job_deducted:
                        deduct_w = self._current_job_grams or self.last_job_grams
                        if deduct_w > 0:
                            active_key = self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            new_w = round(old_w - deduct_w, 2)
                            self.set_slot_grams(new_w, active_key)
                            self._job_deducted = True
                            self.last_job_grams = deduct_w
                            logger.info(f"💾 Auto-deducted {deduct_w}g on FINISH from AMS Slot {active_key} for [{self.name}]. Old: {old_w}g -> New: {new_w}g")
                            self._trigger_save()

                    if self.finish_timestamp == 0.0:
                        self.finish_timestamp = time.time()

                    cost_info = self.calculate_job_cost(self.last_job_grams or 10.0)
                    entry = {
                        "timestamp": time.time(),
                        "printer_name": self.name,
                        "subtask_name": self.subtask_name or "Модель",
                        "weight_g": self.last_job_grams or 0.0,
                        "filament_type": self.filament_type,
                        "cost_uah": cost_info["total_cost"]
                    }
                    if self._main_loop and self._main_loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.storage.add_history_entry(entry), self._main_loop)

                elif self.gcode_state != "FINISH":
                    self.finish_timestamp = 0.0
                self._is_printing = False
                self._job_deducted = False
                self._ftps_attempted = False
                self._current_job_grams = 0.0

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
        payload = json.dumps({
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "print_speed",
                "param": param_str
            }
        })
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
        payload = json.dumps({
            "system": {
                "sequence_id": str(int(time.time())),
                "command": "ledctrl",
                "led_node": "chamber_light",
                "led_mode": new_mode,
                "led_on_time": 500,
                "led_off_time": 500,
                "loop_times": 0,
                "interval_time": 0
            }
        })
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
        
        # 1. Native Bambu Lab calibration command (Option 63 = Full Calibration)
        payload_cal = json.dumps({
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "calibration",
                "option": 63
            }
        })
        self._client.publish(f"device/{self.serial_number}/request", payload_cal)

        # 2. Backup G32 gcode_line command for compatibility across firmware versions
        payload_g32 = json.dumps({
            "print": {
                "sequence_id": str(int(time.time()) + 1),
                "command": "gcode_line",
                "param": "G32\n"
            }
        })
        self._client.publish(f"device/{self.serial_number}/request", payload_g32)
        logger.info(f"🎯 Triggered automatic calibration (G32 / option 63) for [{self.name}] ({self.serial_number})")
        return True

    async def start_print_job_async(self, file_bytes: bytes, filename: str, plate_name: str = "plate_1.gcode", use_ams: bool = True) -> tuple[bool, str]:
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

        # Wait 2.0s for printer firmware to finalize MicroSD FAT32 flush
        await asyncio.sleep(2.0)

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
        sub_path = "Metadata/slice_info.config"
        if zipfile.is_zipfile(io.BytesIO(file_bytes)):
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    names = zf.namelist()
                    if plate_name and f"Metadata/{plate_name}" in names:
                        sub_path = f"Metadata/{plate_name}"
                    elif plate_name and plate_name in names:
                        sub_path = plate_name
                    elif "Metadata/slice_info.config" in names:
                        sub_path = "Metadata/slice_info.config"
                    else:
                        gc_meta = [n for n in names if n.startswith("Metadata/") and n.endswith(".gcode")]
                        if gc_meta:
                            sub_path = gc_meta[0]
            except Exception as e_zip:
                logger.warning(f"Failed zip sub_path scan for {filename}: {e_zip}")

        md5_str = hashlib.md5(file_bytes).hexdigest()
        clean_subtask = re.sub(r'[^a-zA-Z0-9_]', '_', filename.rsplit('.', 1)[0])

        payload = {
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "project_file",
                "param": sub_path,
                "subtask_name": clean_subtask,
                "url": url_path,
                "file": remote_path,
                "md5": md5_str,
                "timelapse": True,
                "bed_type": "auto",
                "use_ams": use_ams
            }
        }

        try:
            self._client.publish(f"device/{self.serial_number}/request", json.dumps(payload))
            logger.info(f"🚀 Sent MQTT project_file command for {clean_file} (url: {url_path}, md5: {md5_str}) to [{self.name}]")
            return True, f"✅ Файл <code>{html.escape(filename)}</code> успішно відправлено по FTPS та запущено на друк на <b>{html.escape(self.name)}</b>!"
        except Exception as e:
            logger.error(f"Error publishing MQTT project_file for [{self.name}]: {e}")
            return False, f"⚠️ Помилка відправки MQTT команди на друк: {e}"

    def calculate_job_cost(self, weight_grams: float, print_mins: int = 0) -> Dict[str, float]:
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
            "total_cost": round(filament_cost + electricity_cost, 2)
        }

    def record_print_hours(self, hours: float):
        """Records completed print hours towards total and maintenance counters."""
        if hours <= 0:
            return
        self.total_print_hours = round(self.total_print_hours + hours, 2)
        self.maintenance_hours_counter = round(self.maintenance_hours_counter + hours, 2)
        for k, item in self.maintenance_items.items():
            item["counter_hours"] = round(item.get("counter_hours", 0.0) + hours, 2)
        logger.info(f"⏱️ Updated print hours for [{self.name}]: +{hours:.2f}h (Total: {self.total_print_hours:.1f}h)")
        self._trigger_save()

    def reset_maintenance_counter(self, item_key: str = "rails"):
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

    def set_maintenance_interval(self, item_key: str, interval_hours: float):
        """Sets target maintenance interval in hours for a specific item."""
        val = max(1.0, float(interval_hours))
        if item_key in self.maintenance_items:
            self.maintenance_items[item_key]["interval_hours"] = val
        if item_key == "rails":
            self.maintenance_interval_hours = int(val)
        logger.info(f"⚙️ Maintenance interval for [{self.name}] ({item_key}) set to {val}h")
        self._trigger_save()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "accessCode": "••••••••" if self.access_code else "",
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
            "gcode_state": self.gcode_state,
            "nozzle_temper": self.nozzle_temper,
            "bed_temper": self.bed_temper,
            "mc_percent": self.mc_percent,
            "mc_remaining_time": self.mc_remaining_time,
            "layer_num": self.layer_num,
            "total_layer_num": self.total_layer_num,
            "subtask_name": self.subtask_name,
            "filament_type": self.filament_type,
            "spd_lvl": self.spd_lvl,
            "spd_mag": self.spd_mag,
            "ams_slots": self.ams_slots
        }
