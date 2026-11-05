"""
Hardware control and operational command execution mixin for Bambu printers.
Encapsulates remote pause/resume/stop, speed levels, chamber light control,
filament loading/unloading sequences, calibration, and plate object skipping.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any

import paho.mqtt.client as mqtt

from config import logger


class PrinterCommandsMixin:
    """Mixin providing hardware control and remote execution methods for BambuPrinter."""

    _client: Any
    serial_number: str | None
    name: str
    id: str
    is_printing: bool
    gcode_state: str
    has_ams: bool
    chamber_light_state: str
    spd_lvl: int
    skipped_objects: list[int]
    current_job_objects: list[dict[str, Any]]
    tray_event_callback: Any
    _pending_tray_events: list[dict]
    _trays_initialized: bool
    _known_trays_state: dict[str, dict]
    ams_trays_info: dict

    def _get_active_event_loop(self) -> asyncio.AbstractEventLoop | None:
        return getattr(self, "_main_loop", None)

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

    def stop(self) -> bool:
        return self.stop_print()

    def _get_filament_temp(self, slot_id: int | str | None = None) -> int:
        """Determines extrusion/purge temperature based on slot or filament type (default 220°C)."""
        if getattr(self, "nozzle_target_temper", 0) and self.nozzle_target_temper >= 170:
            return int(self.nozzle_target_temper)

        slot_str = str(slot_id).strip().lower() if slot_id is not None else ""
        fil_type = ""

        if hasattr(self, "ams_trays_info") and isinstance(self.ams_trays_info, dict) and slot_str in self.ams_trays_info:
            tray_val = self.ams_trays_info[slot_str]
            if isinstance(tray_val, dict):
                fil_type = str(tray_val.get("type") or tray_val.get("tray_type") or "").strip().upper()

        if not fil_type or fil_type in ["", "EMPTY", "НЕВИЗНАЧЕНО"]:
            fil_type = str(getattr(self, "filament_type", "")).strip().upper()

        if "PETG" in fil_type:
            return 235
        elif "ABS" in fil_type or "ASA" in fil_type:
            return 250
        elif "PC" in fil_type:
            return 260
        elif "TPU" in fil_type:
            return 220
        elif "PA" in fil_type or "NYLON" in fil_type:
            return 260
        return 220

    def unload_filament(self, slot_id: int | str | None = None, target_temp: int | None = None) -> bool:
        """Commands printer to unload filament."""
        if self.is_printing or self.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
            logger.warning(f"⚠️ Cannot unload filament on [{self.name}]: printer is active ({self.gcode_state})")
            return False
        if not self._client or not self._client.is_connected():
            logger.warning(f"⚠️ Cannot unload filament on [{self.name}]: MQTT not connected")
            return False

        seq = int(time.time())
        temp = int(target_temp) if target_temp and int(target_temp) >= 170 else self._get_filament_temp(slot_id)
        slot_str = str(slot_id).strip().lower() if slot_id is not None else ""

        payload_unload = json.dumps({"print": {"sequence_id": str(seq), "command": "unload_filament"}})
        self._client.publish(f"device/{self.serial_number}/request", payload_unload)

        if (slot_str in ["0", "1", "2", "3"] and self.has_ams) or (self.has_ams and slot_str not in ["254", "255", "vt", "external"]):
            payload_ams = json.dumps({
                "print": {
                    "sequence_id": str(seq + 1),
                    "command": "ams_change_filament",
                    "target": 255,
                    "curr_temp": temp,
                    "tar_temp": temp,
                }
            })
            self._client.publish(f"device/{self.serial_number}/request", payload_ams)
        else:
            unload_gcode = f"M109 S{temp}\nM83\nG1 E5 F150\nG1 E-80 F800\nM400\nM82\nM104 S0\n"
            payload_gcode_line = json.dumps({
                "print": {
                    "sequence_id": str(seq + 1),
                    "command": "gcode_line",
                    "param": unload_gcode,
                }
            })
            self._client.publish(f"device/{self.serial_number}/request", payload_gcode_line)

        payload_gcode = json.dumps({
            "print": {
                "sequence_id": str(seq + 2),
                "command": "gcode_file",
                "param": "/usr/etc/print/filament_unload.gcode",
            }
        })
        self._client.publish(f"device/{self.serial_number}/request", payload_gcode)
        logger.info(f"📤 Sent Unload Filament commands to [{self.name}] for slot {slot_id} (temp: {temp}°C)")
        return True

    def load_filament(self, slot_id: int | str | None = None, target_temp: int | None = None) -> bool:
        """Commands printer to load filament into the extruder."""
        if self.is_printing or self.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
            logger.warning(f"⚠️ Cannot load filament on [{self.name}]: printer is active ({self.gcode_state})")
            return False
        if not self._client or not self._client.is_connected():
            logger.warning(f"⚠️ Cannot load filament on [{self.name}]: MQTT not connected")
            return False

        seq = int(time.time())
        temp = int(target_temp) if target_temp and int(target_temp) >= 170 else self._get_filament_temp(slot_id)
        slot_str = str(slot_id).strip().lower() if slot_id is not None else ""
        tray_target = int(slot_str) if slot_str in ["0", "1", "2", "3"] else None

        if tray_target is not None and self.has_ams:
            payload_ams = json.dumps({
                "print": {
                    "sequence_id": str(seq),
                    "command": "ams_change_filament",
                    "target": tray_target,
                    "curr_temp": temp,
                    "tar_temp": temp,
                }
            })
            self._client.publish(f"device/{self.serial_number}/request", payload_ams)
        else:
            load_gcode = f"M109 S{temp}\nM83\nG1 E80 F200\nM400\nM82\nM104 S0\n"
            payload_gcode_line = json.dumps({
                "print": {
                    "sequence_id": str(seq),
                    "command": "gcode_line",
                    "param": load_gcode,
                }
            })
            self._client.publish(f"device/{self.serial_number}/request", payload_gcode_line)

        payload_gcode = json.dumps({
            "print": {
                "sequence_id": str(seq + 1),
                "command": "gcode_file",
                "param": "/usr/etc/print/filament_load.gcode",
            }
        })
        self._client.publish(f"device/{self.serial_number}/request", payload_gcode)
        logger.info(f"📥 Sent Load Filament commands to [{self.name}] for slot {slot_id} (temp: {temp}°C)")
        return True

    def _is_tray_loaded(self, t_info: dict) -> bool:
        if not isinstance(t_info, dict):
            return False
        if "empty" in t_info:
            return not bool(t_info.get("empty"))
        t_type = str(t_info.get("type") or t_info.get("tray_type") or "").strip().lower()
        if not t_type or t_type in ["empty", "null", "none"]:
            return False
        return True

    def _check_tray_state_deltas(self) -> None:
        """Detects physical tray unload and load events based on live MQTT telemetry."""
        curr_trays = dict(self.ams_trays_info)
        if not getattr(self, "_trays_initialized", False):
            for k, t_data in curr_trays.items():
                if isinstance(t_data, dict):
                    self._known_trays_state[str(k)] = {
                        "loaded": self._is_tray_loaded(t_data),
                        "type": str(t_data.get("type") or t_data.get("tray_type") or "").strip(),
                        "color": str(t_data.get("color") or "").strip(),
                        "tray_color": str(t_data.get("tray_color") or "").strip(),
                    }
            if curr_trays:
                self._trays_initialized = True
            return

        for k, t_data in curr_trays.items():
            if not isinstance(t_data, dict):
                continue
            k_str = str(k)
            now_loaded = self._is_tray_loaded(t_data)
            now_type = str(t_data.get("type") or t_data.get("tray_type") or "").strip()
            now_color = str(t_data.get("color") or "").strip()
            now_tray_color = str(t_data.get("tray_color") or "").strip()

            was_state = self._known_trays_state.get(k_str)
            if was_state is not None:
                was_loaded = was_state.get("loaded", False)
                was_type = was_state.get("type", "")

                if was_loaded and not now_loaded:
                    event = {
                        "event": "tray_unloaded",
                        "printer_id": self.id,
                        "printer_name": self.name,
                        "slot_id": k_str,
                        "prev_type": was_type,
                        "timestamp": time.time(),
                    }
                    logger.info(f"🔄 [Filament Auto] Tray {k_str} on [{self.name}] unloaded on hardware")
                    self._dispatch_tray_event(event)
                elif (not was_loaded and now_loaded) or (now_loaded and not was_type and now_type):
                    event = {
                        "event": "tray_loaded",
                        "printer_id": self.id,
                        "printer_name": self.name,
                        "slot_id": k_str,
                        "filament_type": now_type,
                        "color": now_color,
                        "tray_color": now_tray_color,
                        "tray_info": dict(t_data),
                        "timestamp": time.time(),
                    }
                    logger.info(f"🔄 [Filament Auto] Tray {k_str} on [{self.name}] loaded on hardware ({now_type})")
                    self._dispatch_tray_event(event)

            self._known_trays_state[k_str] = {
                "loaded": now_loaded,
                "type": now_type,
                "color": now_color,
                "tray_color": now_tray_color,
            }

    def _dispatch_tray_event(self, event: dict) -> None:
        if self.tray_event_callback:
            loop_to_use = getattr(self, "_main_loop", None) or self._get_active_event_loop()
            if loop_to_use and loop_to_use.is_running():
                try:
                    if inspect.iscoroutinefunction(self.tray_event_callback):
                        asyncio.run_coroutine_threadsafe(self.tray_event_callback(self, event), loop_to_use)
                    else:
                        loop_to_use.call_soon_threadsafe(self.tray_event_callback, self, event)
                except Exception as e:
                    logger.warning(f"Failed dispatching tray event for [{self.name}]: {e}")
            elif not inspect.iscoroutinefunction(self.tray_event_callback):
                try:
                    self.tray_event_callback(self, event)
                except Exception as e:
                    logger.warning(f"Failed direct callback dispatch for [{self.name}]: {e}")
        else:
            self._pending_tray_events.append(event)

    def pop_tray_events(self) -> list[dict]:
        events = list(self._pending_tray_events)
        self._pending_tray_events.clear()
        return events

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
        if mode == "toggle":
            new_mode = "off" if self.chamber_light_state == "on" else "on"
        else:
            new_mode = "on" if str(mode).lower() in ["on", "1", "true"] else "off"
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

    def invalidate_plate_gif_cache(self) -> None:
        """Clears cached animated GIF for plate map."""
        from services.printer_file_job_service import invalidate_plate_gif_cache
        invalidate_plate_gif_cache(self)

    def get_clean_job_objects(self) -> list[dict[str, Any]]:
        """Returns only valid printable model objects for current job, purging wipe towers / auxiliary meshes."""
        objs = getattr(self, "current_job_objects", [])
        if not objs:
            return []

        filtered = []
        for o in objs:
            n_low = str(o.get("name", "")).lower()
            if any(k in n_low for k in [
                "wipe tower", "prime tower", "purge tower", "wipe_tower", "prime_tower",
                "flush volume", "purge volume", "timelapse", "calibration line", "leveling line", "test_line"
            ]):
                continue
            bbox = o.get("bbox")
            if bbox and isinstance(bbox, list) and len(bbox) >= 4:
                try:
                    w = abs(float(bbox[2]) - float(bbox[0]))
                    h = abs(float(bbox[3]) - float(bbox[1]))
                    if w < 3.0 or h < 3.0 or (w * h) < 9.0:
                        continue
                except Exception:
                    pass
            filtered.append(o)

        if not filtered and objs:
            filtered = objs

        if len(filtered) != len(self.current_job_objects):
            self.current_job_objects = filtered
            self.invalidate_plate_gif_cache()

        return self.current_job_objects

    def get_plate_gif(self) -> bytes:
        """Returns cached animated GIF of plate objects highlighting each object sequentially."""
        from services.printer_file_job_service import render_plate_gif_cached
        return render_plate_gif_cached(self)

    def start_calibration(self) -> bool:
        """Triggers full automatic Bambu Lab calibration (vibration frequency + auto bed leveling)."""
        if not self._client or not self._client.is_connected():
            return False

        setattr(self, "_is_calibrating", True)
        setattr(self, "_job_deducted", True)
        setattr(self, "_current_job_grams", 0.0)

        payload_cal = json.dumps(
            {"print": {"sequence_id": str(int(time.time())), "command": "calibration", "option": 63}}
        )
        self._client.publish(f"device/{self.serial_number}/request", payload_cal)

        payload_g32 = json.dumps(
            {"print": {"sequence_id": str(int(time.time()) + 1), "command": "gcode_line", "param": "G32\n"}}
        )
        self._client.publish(f"device/{self.serial_number}/request", payload_g32)
        logger.info(f"🎯 Triggered automatic calibration for [{self.name}] ({self.serial_number})")
        return True

    async def skip_objects_async(self, obj_ids: list[int]) -> tuple[bool, str]:
        """Sends MQTT print.skip_objects command to skip specific object IDs on the current plate."""
        is_conn = (self._client and hasattr(self._client, "is_connected") and self._client.is_connected()) or getattr(self, "is_mqtt_connected", False)
        if not self._client or not is_conn:
            return False, "Принтер не підключений по MQTT або вимкнений"
        if not self.serial_number:
            return False, "Серійний номер принтера не вказано"
        if not obj_ids or not isinstance(obj_ids, list):
            return False, "Необхідно вказати список ID об'єктів для пропуску"

        int_obj_ids = [int(i) for i in obj_ids if str(i).isdigit()]
        if not int_obj_ids:
            return False, "Список ID об'єктів порожній або некоректний"

        current_skipped = [int(i) for i in getattr(self, "skipped_objects", []) if str(i).isdigit()]
        all_skipped = list(dict.fromkeys(current_skipped + int_obj_ids))

        payload = {
            "print": {
                "sequence_id": str(int(time.time())),
                "command": "skip_objects",
                "obj_list": all_skipped,
            }
        }
        topic = f"device/{self.serial_number}/request"
        try:
            result = self._client.publish(topic, json.dumps(payload), qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                return False, f"Не вдалося відправити MQTT команду (код {result.rc})"
        except Exception as e:
            return False, f"Помилка відправки команди: {e}"

        self.skipped_objects = all_skipped
        skipped_at = getattr(self, "_skipped_at_progress", None)
        if not isinstance(skipped_at, dict):
            skipped_at = {}
            setattr(self, "_skipped_at_progress", skipped_at)
        curr_pct = max(0, min(100, int(getattr(self, "mc_percent", getattr(self, "progress", 0)) or 0)))
        for oid in int_obj_ids:
            if oid not in skipped_at:
                skipped_at[oid] = curr_pct

        self.invalidate_plate_gif_cache()

        logger.info(f"🚫 Sent skip_objects {all_skipped} to printer [{self.name}] ({self.serial_number})")
        msg = f"Об'єкт(и) {int_obj_ids} успішно пропущено"
        if self.is_all_objects_skipped():
            msg += " ⚠️ Увага: всі об'єкти на столі пропущено! Рекомендується зупинити друк."
        return True, msg

    def is_all_objects_skipped(self) -> bool:
        """Returns True if there are known real printable objects and all of them have been skipped."""
        real_objs = [o for o in self.get_clean_job_objects() if not o.get("_synthetic")]
        if not real_objs:
            return False
        skipped_set = {str(s) for s in getattr(self, "skipped_objects", [])}
        return all(str(o.get("id")) in skipped_set for o in real_objs)

    def calculate_effective_job_grams(self, base_grams: float) -> tuple[float, float]:
        """
        Calculates (effective_grams, saved_grams) accounting for skipped objects on the plate
        and the print progress percentage at which each object was skipped.
        """
        if base_grams <= 0.0:
            return 0.0, 0.0
        skipped_raw = getattr(self, "skipped_objects", []) or []
        skipped_set = {str(x) for x in skipped_raw if str(x).isdigit()}
        if not skipped_set:
            return round(base_grams, 2), 0.0

        real_objs = [o for o in self.get_clean_job_objects() if not o.get("_synthetic")]
        if not real_objs:
            return round(base_grams, 2), 0.0

        skipped_at: dict[int, int] = getattr(self, "_skipped_at_progress", {}) or {}
        n_objs = len(real_objs)
        total_explicit_w = sum(float(o.get("weight_g", 0.0) or 0.0) for o in real_objs)

        saved_fraction = 0.0
        for o in real_objs:
            oid_str = str(o.get("id", ""))
            if total_explicit_w > 0 and float(o.get("weight_g", 0.0) or 0.0) > 0:
                share = float(o["weight_g"]) / total_explicit_w
            else:
                share = 1.0 / n_objs

            if oid_str in skipped_set:
                oid_int = int(oid_str) if oid_str.isdigit() else -1
                if oid_int in skipped_at:
                    pct_at_skip = max(0, min(100, int(skipped_at[oid_int])))
                else:
                    raw_pct = int(getattr(self, "mc_percent", getattr(self, "progress", 0)) or 0)
                    pct_at_skip = 0 if raw_pct >= 100 else max(0, min(100, raw_pct))
                unprinted_ratio = max(0.0, min(1.0, (100.0 - pct_at_skip) / 100.0))
                saved_fraction += share * unprinted_ratio

        saved_grams = round(base_grams * max(0.0, min(1.0, saved_fraction)), 2)
        effective_grams = max(0.0, round(base_grams - saved_grams, 2))
        return effective_grams, saved_grams

    async def start_print_job_async(
        self,
        file_bytes: bytes,
        filename: str,
        plate_name: str = "plate_1.gcode",
        use_ams: bool = True,
        part_name: str | None = None,
        ams_slot: int | str | None = None,
        ams_mapping: list[int] | None = None,
        weight_g: float | None = None,
    ) -> tuple[bool, str]:
        """Uploads 3MF file via FTPS to printer SD card and publishes MQTT project_file command to start printing."""
        from services.printer_file_job_service import start_print_job

        return await start_print_job(
            printer=self,
            file_bytes=file_bytes,
            filename=filename,
            plate_name=plate_name,
            use_ams=use_ams,
            part_name=part_name,
            ams_slot=ams_slot,
            ams_mapping=ams_mapping,
            weight_g=weight_g,
        )
