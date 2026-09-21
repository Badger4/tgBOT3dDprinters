"""
Printer remote control, actions, speed levels, maintenance, and calibration endpoints.
"""

import time

from aiohttp import web

from config import logger
from services.http.auth import check_auth


async def handle_printer_control(request: web.Request) -> web.Response:
    """POST /api/printers/{id}/control - Remote actions."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    try:
        data = await request.json()
        action = str(data.get("action", "")).lower()
    except Exception:
        return web.json_response({"error": "Invalid JSON payload"}, status=400)

    if action == "pause":
        p.pause()
        return web.json_response({"status": "ok", "action": "pause"})
    elif action == "resume":
        p.resume()
        return web.json_response({"status": "ok", "action": "resume"})
    elif action == "stop":
        p.stop_print()
        return web.json_response({"status": "ok", "action": "stop"})
    elif action == "light_toggle":
        p.toggle_chamber_light("toggle")
        return web.json_response({"status": "ok", "action": "light_toggle", "light_state": p.chamber_light_state})
    elif action == "toggle_notify":
        p.notify = not getattr(p, "notify", True)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "toggle_notify", "notify": p.notify})
    elif action == "set_speed":
        level = int(data.get("level", 2))
        p.set_speed_level(level)
        return web.json_response({"status": "ok", "action": "set_speed", "level": level})
    elif action == "reset_maint":
        item_key = str(data.get("item_key", "rails"))
        p.reset_maintenance_counter(item_key)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "reset_maint", "item_key": item_key})
    elif action == "set_maint_interval":
        item_key = str(data.get("item_key", "rails"))
        interval = float(data.get("interval_hours", 100.0))
        p.set_maintenance_interval(item_key, interval)
        await app_obj.save_printers_config()
        return web.json_response(
            {"status": "ok", "action": "set_maint_interval", "item_key": item_key, "interval_hours": interval}
        )
    elif action in ["set_filament", "set_slot_grams"]:
        grams = float(data.get("grams", 1000.0))
        raw_slot = data.get("slot_id")
        slot_id = str(raw_slot) if raw_slot is not None else "255"
        p.set_slot_grams(grams, slot_id=raw_slot if raw_slot is not None else "255")

        spools = await app_obj.storage.load_spools()
        for s_id, s in spools.items():
            if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == slot_id:
                prev_w = float(s.get("remaining_grams", 0.0))
                new_w = round(float(grams), 1)
                s["remaining_grams"] = new_w
                spools[s_id] = s
                if abs(new_w - prev_w) > 0.01:
                    delta = new_w - prev_w
                    await app_obj.storage.record_spool_movement(
                        spool_id=s_id,
                        spool_name=s.get("name", "Котушка"),
                        action="refill" if delta > 0 else "manual_edit",
                        weight_change_g=round(delta, 2),
                        prev_weight_g=round(prev_w, 2),
                        new_weight_g=round(new_w, 2),
                        reason=f"Коригування ваги слоту {slot_id} (Web)",
                        user="Admin",
                    )
        await app_obj.storage.save_spools(spools)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": action, "grams": grams, "slot_id": raw_slot if raw_slot is not None else "255"})
    elif action == "assign_spool":
        spool_id = str(data.get("spool_id", ""))
        raw_slot = data.get("slot_id")
        slot_id = str(raw_slot) if raw_slot is not None else "255"
        spools = await app_obj.storage.load_spools()
        spool = spools.get(spool_id)
        if not spool:
            return web.json_response({"error": "Котушку не знайдено на складі"}, status=404)

        # Unassign any previously mounted spool from this printer slot
        current_slot_grams = p.get_slot_grams(slot_id) if hasattr(p, "get_slot_grams") else 1000.0
        for s_id, s in list(spools.items()):
            if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == slot_id and s_id != spool_id:
                init_g = float(s.get("initial_grams", s.get("remaining_grams", 1000.0)))
                weight_unchanged = round(float(current_slot_grams), 1) >= round(init_g, 1)
                if weight_unchanged:
                    parent_id = s.get("parent_spool_id")
                    parent_spool = spools.get(parent_id) if parent_id else None
                    if not parent_spool:
                        for other_id, other_s in spools.items():
                            if (
                                not other_s.get("assigned_printer_id")
                                and other_s.get("name") == s.get("name")
                                and other_s.get("type") == s.get("type")
                                and other_s.get("color") == s.get("color")
                                and round(float(other_s.get("remaining_grams", 0)), 1) == round(init_g, 1)
                            ):
                                parent_spool = other_s
                                break
                    if parent_spool and not parent_spool.get("assigned_printer_id"):
                        parent_spool["quantity"] = int(parent_spool.get("quantity", 1)) + 1
                        spools[parent_spool["id"]] = parent_spool
                        if s["id"] != parent_spool["id"] and s["id"] in spools:
                            del spools[s["id"]]
                    else:
                        s["assigned_printer_id"] = None
                        s["assigned_slot_key"] = None
                        s["remaining_grams"] = round(init_g, 1)
                        s["quantity"] = max(1, int(s.get("quantity", 1)))
                        spools[s_id] = s
                else:
                    s["assigned_printer_id"] = None
                    s["assigned_slot_key"] = None
                    s["remaining_grams"] = round(float(current_slot_grams), 1)
                    s["quantity"] = 1
                    s.pop("parent_spool_id", None)
                    spools[s_id] = s

        grams = float(spool.get("remaining_grams", 1000.0))
        p.set_slot_grams(grams, slot_id=raw_slot if raw_slot is not None else "255")
        if spool.get("type"):
            p.filament_type = str(spool.get("type"))
        if spool.get("price_per_kg") or spool.get("price_uah"):
            p.price_per_kg = float(spool.get("price_per_kg") or spool.get("price_uah"))

        qty = max(1, int(spool.get("quantity", 1)))
        if qty > 1:
            spool["quantity"] = qty - 1
            spools[spool_id] = spool

            assigned_spool_id = f"spool_{int(time.time() * 1000)}"
            assigned_spool = spool.copy()
            assigned_spool["id"] = assigned_spool_id
            assigned_spool["parent_spool_id"] = spool_id
            assigned_spool["quantity"] = 1
            assigned_spool["assigned_printer_id"] = p.id
            assigned_spool["assigned_slot_key"] = slot_id
            if "initial_grams" not in assigned_spool:
                assigned_spool["initial_grams"] = grams
            spools[assigned_spool_id] = assigned_spool
            p.active_spool_id = assigned_spool_id
            target_spool = assigned_spool
        else:
            spool["assigned_printer_id"] = p.id
            spool["assigned_slot_key"] = slot_id
            spool["quantity"] = 1
            if "initial_grams" not in spool:
                spool["initial_grams"] = grams
            spools[spool_id] = spool
            p.active_spool_id = spool_id
            target_spool = spool

        await app_obj.storage.save_spools(spools)
        await app_obj.save_printers_config()

        if data.get("load_hardware") is True and hasattr(p, "load_filament"):
            if not (getattr(p, "is_printing", False) or p.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]):
                p.load_filament(slot_id=raw_slot)

        return web.json_response({"status": "ok", "action": "assign_spool", "spool": target_spool, "slot_id": raw_slot if raw_slot is not None else "255"})
    elif action == "unassign_spool":
        raw_slot = data.get("slot_id") or data.get("slot_key")
        slot_id = str(raw_slot) if raw_slot is not None else "255"
        slot_grams = p.get_slot_grams(slot_id) if hasattr(p, "get_slot_grams") else 1000.0
        spools = await app_obj.storage.load_spools()
        for s_id, s in list(spools.items()):
            if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == slot_id:
                init_g = float(s.get("initial_grams", s.get("remaining_grams", 1000.0)))
                weight_unchanged = round(float(slot_grams), 1) >= round(init_g, 1)
                if weight_unchanged:
                    parent_id = s.get("parent_spool_id")
                    parent_spool = spools.get(parent_id) if parent_id else None
                    if not parent_spool:
                        for other_id, other_s in spools.items():
                            if (
                                not other_s.get("assigned_printer_id")
                                and other_s.get("name") == s.get("name")
                                and other_s.get("type") == s.get("type")
                                and other_s.get("color") == s.get("color")
                                and round(float(other_s.get("remaining_grams", 0)), 1) == round(init_g, 1)
                            ):
                                parent_spool = other_s
                                break
                    if parent_spool and not parent_spool.get("assigned_printer_id"):
                        parent_spool["quantity"] = int(parent_spool.get("quantity", 1)) + 1
                        spools[parent_spool["id"]] = parent_spool
                        if s["id"] != parent_spool["id"] and s["id"] in spools:
                            del spools[s["id"]]
                    else:
                        s["assigned_printer_id"] = None
                        s["assigned_slot_key"] = None
                        s["remaining_grams"] = round(init_g, 1)
                        s["quantity"] = max(1, int(s.get("quantity", 1)))
                        spools[s_id] = s
                else:
                    s["assigned_printer_id"] = None
                    s["assigned_slot_key"] = None
                    s["remaining_grams"] = round(float(slot_grams), 1)
                    s["quantity"] = 1
                    s.pop("parent_spool_id", None)
                    spools[s_id] = s
        await app_obj.storage.save_spools(spools)
        if hasattr(p, "set_slot_grams"):
            p.set_slot_grams(0.0, slot_id=slot_id)
        if hasattr(p, "ams_slots") and isinstance(p.ams_slots, dict):
            p.ams_slots[slot_id] = 0.0
        await app_obj.save_printers_config()

        if data.get("unload_hardware") is True and hasattr(p, "unload_filament"):
            if not (getattr(p, "is_printing", False) or p.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]):
                p.unload_filament(slot_id=slot_id)

        return web.json_response(
            {
                "status": "ok",
                "action": "unassign_spool",
                "slot_id": slot_id,
                "remaining_grams": 0.0,
            }
        )
    elif action == "unload_filament":
        raw_slot = data.get("slot_id") or data.get("slot_key")
        if getattr(p, "is_printing", False) or p.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
            return web.json_response({"error": "Неможливо вивантажити: принтер зараз виконує друк!"}, status=400)
        success = p.unload_filament(slot_id=raw_slot)
        return web.json_response({"status": "ok" if success else "error", "action": "unload_filament", "slot_id": raw_slot})
    elif action == "load_filament":
        raw_slot = data.get("slot_id") or data.get("slot_key")
        target_temp = data.get("target_temp") or data.get("temp")
        if getattr(p, "is_printing", False) or p.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
            return web.json_response({"error": "Неможливо завантажити: принтер зараз виконує друк!"}, status=400)
        success = p.load_filament(slot_id=raw_slot, target_temp=target_temp)
        return web.json_response({"status": "ok" if success else "error", "action": "load_filament", "slot_id": raw_slot})
    elif action == "set_ams_enabled":
        enabled = bool(data.get("enabled", False))
        p.ams_enabled = enabled
        await app_obj.save_printers_config()
        logger.info(f"⚙️ Set ams_enabled={enabled} for [{p.name}]")
        return web.json_response(
            {"status": "ok", "action": "set_ams_enabled", "enabled": enabled, "has_ams": p.has_ams}
        )
    elif action == "calibrate":
        if p.gcode_state == "RUNNING":
            return web.json_response({"error": "Неможливо запустити калібрування під час друку!"}, status=400)
        ok = p.start_calibration()
        if ok:
            return web.json_response({"status": "ok", "action": "calibrate", "message": "Запущено авто-калібрування!"})
        else:
            return web.json_response(
                {"error": "Не вдалося запустити калібрування (перевірте MQTT з'єднання)"}, status=500
            )
    elif action == "skip_objects":
        obj_ids = data.get("obj_ids") or data.get("obj_list") or []
        if not obj_ids or not isinstance(obj_ids, list):
            return web.json_response({"error": "obj_ids є обов'язковим списком цілих чисел"}, status=400)
        ok, msg = await p.skip_objects_async(obj_ids)
        if ok:
            return web.json_response({
                "status": "ok",
                "action": "skip_objects",
                "message": msg,
                "skipped_objects": p.skipped_objects,
            })
        return web.json_response({"error": msg}, status=400)
    else:
        return web.json_response({"error": f"Unknown action '{action}'"}, status=400)


async def handle_fleet_lights(request: web.Request) -> web.Response:
    """POST /api/fleet/lights - Toggle or set chamber light across all connected printers."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    mode = "toggle"
    try:
        if request.can_read_body:
            data = await request.json()
            if isinstance(data, dict):
                mode = str(data.get("mode", "toggle")).lower()
    except Exception:
        mode = "toggle"

    updated = []
    skipped = []
    for pid, p in app_obj.printers.items():
        is_online = getattr(p, "is_online", True) and getattr(p, "mapped_state", "ONLINE") != "OFFLINE"
        if not is_online:
            skipped.append({"id": pid, "name": getattr(p, "name", pid), "reason": "offline"})
            continue
        try:
            if hasattr(p, "toggle_chamber_light"):
                p.toggle_chamber_light(mode)
            elif hasattr(p, "toggle_light"):
                p.toggle_light()
            updated.append({
                "id": pid,
                "name": getattr(p, "name", pid),
                "light_state": getattr(p, "chamber_light_state", "unknown"),
            })
        except Exception as e:
            logger.error(f"Error setting light for [{pid}]: {e}")
            skipped.append({"id": pid, "name": getattr(p, "name", pid), "reason": str(e)})

    return web.json_response({
        "status": "ok",
        "mode": mode,
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "printers": updated,
        "skipped": skipped,
    })


async def handle_fleet_calibrate(request: web.Request) -> web.Response:
    """POST /api/fleet/calibrate - Run auto-calibration (G32) on all idle online printers."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    calibrated = []
    skipped = []

    for pid, p in app_obj.printers.items():
        is_online = getattr(p, "is_online", True) and getattr(p, "mapped_state", "ONLINE") != "OFFLINE"
        p_name = getattr(p, "name", pid)
        if not is_online:
            skipped.append({"id": pid, "name": p_name, "reason": "offline"})
            continue

        is_printing = getattr(p, "is_printing", False)
        gcode_st = str(getattr(p, "gcode_state", "IDLE")).upper()
        if is_printing or gcode_st in ["RUNNING", "PAUSE", "PREPARE", "PREPARING", "PREPARATION", "BUILDING"]:
            skipped.append({"id": pid, "name": p_name, "reason": "busy", "state": gcode_st})
            continue

        try:
            if hasattr(p, "start_calibration"):
                ok = p.start_calibration()
                if ok:
                    calibrated.append({"id": pid, "name": p_name})
                else:
                    skipped.append({"id": pid, "name": p_name, "reason": "command_failed"})
            else:
                skipped.append({"id": pid, "name": p_name, "reason": "not_supported"})
        except Exception as e:
            logger.error(f"Error starting calibration on [{pid}]: {e}")
            skipped.append({"id": pid, "name": p_name, "reason": str(e)})

    return web.json_response({
        "status": "ok",
        "calibrated_count": len(calibrated),
        "skipped_count": len(skipped),
        "calibrated": calibrated,
        "skipped": skipped,
    })
