"""
Printer REST API routes, telemetry, snapshots, and credential management.
"""

import asyncio
import uuid
from typing import Any

from aiohttp import web

from config import logger
from models.printer import BambuPrinter
from services.camera_stream import async_stream_camera_frames, capture_real_camera_photo
from services.http.auth import check_auth

__all__ = [
    "build_printer_telemetry",
    "handle_get_printers",
    "handle_create_printer",
    "handle_delete_printer",
    "handle_get_printer_by_id",
    "handle_get_printer_plate_map",
    "handle_get_snapshot",
    "handle_get_camera_stream",
    "handle_update_access_code",
]


def build_printer_telemetry(p: Any) -> dict:
    used_w = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
    active_slot = p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "255"
    slot_grams = p.get_slot_grams(active_slot) if hasattr(p, "get_slot_grams") else getattr(p, "filament_grams", 1000.0)
    return {
        "id": p.id,
        "name": p.name,
        "ip": p.ip,
        "serial": p.serial_number,
        "state": p.gcode_state,
        "nozzle_temp": p.nozzle_temper,
        "bed_temp": p.bed_temper,
        "progress_pct": p.mc_percent,
        "remaining_mins": p.mc_remaining_time,
        "current_layer": p.layer_num,
        "total_layers": p.total_layer_num,
        "subtask_name": p.subtask_name or "",
        "filament_type": p.filament_type,
        "filament_grams_left": round(float(slot_grams), 1),
        "job_weight_g": round(used_w, 2),
        "chamber_light_state": getattr(p, "chamber_light_state", "off"),
        "spd_lvl": getattr(p, "spd_lvl", 2),
        "spd_mag": getattr(p, "spd_mag", 100),
        "maintenance_hours_counter": round(getattr(p, "maintenance_hours_counter", 0.0), 1),
        "maintenance_interval_hours": getattr(p, "maintenance_interval_hours", 100),
        "maintenance_items": getattr(p, "maintenance_items", {}),
        "total_print_hours": round(getattr(p, "total_print_hours", 0.0), 1),
        "hms_errors": getattr(p, "hms_errors", []),
        "ams_slots": getattr(p, "ams_slots", {}),
        "ams_trays_info": getattr(p, "ams_trays_info", {}),
        "active_ams_tray": getattr(p, "active_ams_tray", 255),
        "active_slot_key": p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "254",
        "has_ams": bool(getattr(p, "has_ams", False)),
        "notify": getattr(p, "notify", True),
        "current_job_objects": getattr(p, "current_job_objects", []),
        "skipped_objects": getattr(p, "skipped_objects", []),
    }


async def handle_get_printers(request: web.Request) -> web.Response:
    """GET /api/printers - Live telemetry array for WebApp / HA / Grafana."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    result = [build_printer_telemetry(p) for p in app_obj.printers.values()]
    return web.json_response(result)


async def handle_create_printer(request: web.Request) -> web.Response:
    """POST /api/printers - Adds a new Bambu printer."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        name = str(data.get("name", "")).strip()
        ip = str(data.get("ip", "")).strip()
        access_code = str(data.get("accessCode", "")).strip()
        serial_number = str(data.get("serialNumber", "")).strip()
        printer_model = str(data.get("printer_model") or data.get("model") or "A1").strip()

        if not name or not ip or not access_code or not serial_number:
            return web.json_response({"error": "Всі поля (Назва, IP, Access Code, SN) обов'язкові!"}, status=400)

        p_data = {
            "id": str(uuid.uuid4()),
            "name": name,
            "ip": ip,
            "accessCode": access_code,
            "serialNumber": serial_number,
            "printer_model": printer_model,
            "filament_grams": float(data.get("filament_grams", 1000.0)),
            "notify": True,
        }

        p_obj = BambuPrinter(p_data, app_obj.storage, save_callback=app_obj.save_printers_config)
        p_obj.init_mqtt(asyncio.get_running_loop())
        app_obj.printers[p_obj.id] = p_obj
        await app_obj.save_printers_config()

        logger.info(f"➕ Added new printer [{p_obj.name}] ({p_obj.ip}) via WebApp REST API")
        return web.json_response({"status": "ok", "printer": build_printer_telemetry(p_obj)})
    except Exception as e:
        logger.error(f"Error creating printer via API: {e}")
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_printer(request: web.Request) -> web.Response:
    """DELETE /api/printers/{id} - Removes a Bambu printer."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    p.destroy()
    del app_obj.printers[p_id]
    await app_obj.save_printers_config()
    logger.info(f"🗑️ Removed printer [{p.name}] via WebApp REST API")
    return web.json_response({"status": "ok"})


async def handle_get_printer_by_id(request: web.Request) -> web.Response:
    """GET /api/printers/{id} - Single printer telemetry."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    return web.json_response(build_printer_telemetry(p))


async def handle_get_printer_plate_map(request: web.Request) -> web.Response:
    """GET /api/printers/{id}/plate_map - Renders top-down 2D plate map diagram JPEG image."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    printer_id = request.match_info.get("id", "")
    printer = app_obj.printers.get(printer_id)
    if not printer:
        return web.json_response({"error": "Printer not found"}, status=404)

    objects = (
        printer.get_clean_job_objects()
        if hasattr(printer, "get_clean_job_objects")
        else getattr(printer, "current_job_objects", [])
    )
    skipped = getattr(printer, "skipped_objects", [])
    p_model = str(getattr(printer, "printer_model", "") or getattr(printer, "name", "")).lower()
    bed_size = (180, 180) if "mini" in p_model else (256, 256)

    req_fmt = str(request.query.get("format") or request.query.get("gif") or "").lower()
    if req_fmt in ["gif", "1", "true"]:
        img_bytes = printer.get_plate_gif()
        c_type = "image/gif"
    else:
        img_bytes = b""
        c_type = "image/jpeg"

    if not img_bytes:
        from utils.image_utils import render_plate_diagram

        img_bytes = render_plate_diagram(objects, bed_size_mm=bed_size, skipped_ids=skipped)
        c_type = "image/jpeg"

    if not img_bytes:
        return web.Response(status=404, text="Map generation failed")

    return web.Response(
        body=img_bytes,
        content_type=c_type,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


async def handle_get_snapshot(request: web.Request) -> web.Response:
    """GET /api/printers/{id}/snapshot - Live JPEG frame for WebApp / Home Assistant."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    frame = await capture_real_camera_photo(p.ip, p.access_code)
    if not frame:
        return web.json_response({"error": "Failed capturing camera frame"}, status=503)

    return web.Response(body=frame, content_type="image/jpeg")


async def handle_get_camera_stream(request: web.Request) -> web.StreamResponse:
    """GET /api/printers/{id}/stream - Real-time MJPEG camera video stream (multipart/x-mixed-replace)."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "close",
        },
    )
    await response.prepare(request)

    try:
        async for jpeg_bytes in async_stream_camera_frames(p.ip, p.access_code):
            if request.transport and request.transport.is_closing():
                break

            header = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg_bytes)}\r\n\r\n".encode()
            )
            await response.write(header + jpeg_bytes + b"\r\n")
            await asyncio.sleep(0.02)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    except Exception as e:
        logger.warning(f"MJPEG Stream error for [{p.name}]: {e}")

    return response


async def handle_update_access_code(request: web.Request) -> web.Response:
    """POST /api/printers/{id}/access_code - Updates access code &SN for a printer."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    try:
        data = await request.json()
        new_code = str(data.get("accessCode", "")).strip()
        new_sn = str(data.get("serialNumber", "")).strip()
        if new_code:
            p.access_code = new_code
        if new_sn:
            p.serial_number = new_sn

        p.destroy()
        p.init_mqtt(asyncio.get_running_loop())
        await app_obj.save_printers_config()
        logger.info(f"🔑 Updated credentials & reconnected MQTT for [{p.name}] via REST API")
        return web.json_response({"status": "ok"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_get_printer_settings(request: web.Request) -> web.Response:
    """GET /api/printers/{id}/settings - Returns individual settings for a specific printer."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    raw_notify = getattr(p, "notify", True)
    if isinstance(raw_notify, dict):
        notify_dict = {
            "start": bool(raw_notify.get("start", True)),
            "finish": bool(raw_notify.get("finish", True)),
            "pause": bool(raw_notify.get("pause", True)),
            "hms": bool(raw_notify.get("hms", True)),
            "remind_clear": bool(raw_notify.get("remind_clear", True)),
            "min_time_to_end": int(raw_notify.get("min_time_to_end", 0)),
            "min_filament": int(raw_notify.get("min_filament", 0)),
        }
    else:
        is_on = bool(raw_notify)
        notify_dict = {
            "start": is_on,
            "finish": is_on,
            "pause": is_on,
            "hms": is_on,
            "remind_clear": is_on,
            "min_time_to_end": 0,
            "min_filament": 0,
        }

    settings = {
        "id": p.id,
        "name": p.name,
        "ip": p.ip,
        "accessCode": p.access_code,
        "serialNumber": p.serial_number,
        "printer_model": getattr(p, "printer_model", "A1"),
        "ams_enabled": getattr(p, "ams_enabled", None),
        "notify": notify_dict,
        "spd_lvl": getattr(p, "spd_lvl", 2),
        "maintenance_interval_hours": getattr(p, "maintenance_interval_hours", 100),
        "maintenance_hours_counter": round(getattr(p, "maintenance_hours_counter", 0.0), 1),
        "ams_slots": getattr(p, "ams_slots", {}),
        "filament_type": getattr(p, "filament_type", "PLA"),
        "nozzle_diameter": getattr(p, "nozzle_diameter", "0.4"),
    }
    return web.json_response(settings)


async def handle_update_printer_settings(request: web.Request) -> web.Response:
    """POST /api/printers/{id}/settings - Updates individual settings for a specific printer."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    try:
        data = await request.json()
        reconnect_mqtt = False

        if "name" in data and str(data["name"]).strip():
            p.name = str(data["name"]).strip()
        if "ip" in data and str(data["ip"]).strip():
            new_ip = str(data["ip"]).strip()
            if new_ip != p.ip:
                p.ip = new_ip
                reconnect_mqtt = True
        if "accessCode" in data and str(data["accessCode"]).strip():
            new_ac = str(data["accessCode"]).strip()
            if new_ac != p.access_code:
                p.access_code = new_ac
                reconnect_mqtt = True
        if "serialNumber" in data and str(data["serialNumber"]).strip():
            new_sn = str(data["serialNumber"]).strip()
            if new_sn != p.serial_number:
                p.serial_number = new_sn
                reconnect_mqtt = True
        if "printer_model" in data:
            p.printer_model = str(data["printer_model"]).strip()
        if "ams_enabled" in data:
            raw_ams = data["ams_enabled"]
            if raw_ams in [True, "true", "True"]:
                p.ams_enabled = True
            elif raw_ams in [False, "false", "False"]:
                p.ams_enabled = False
            else:
                p.ams_enabled = None
        if "notify" in data:
            raw_n = data["notify"]
            if isinstance(raw_n, dict):
                p.notify = {
                    "start": bool(raw_n.get("start", True)),
                    "finish": bool(raw_n.get("finish", True)),
                    "pause": bool(raw_n.get("pause", True)),
                    "hms": bool(raw_n.get("hms", True)),
                    "remind_clear": bool(raw_n.get("remind_clear", True)),
                    "min_time_to_end": int(raw_n.get("min_time_to_end", 0)),
                    "min_filament": int(raw_n.get("min_filament", 0)),
                }
            else:
                p.notify = bool(raw_n)
        if "spd_lvl" in data:
            p.spd_lvl = int(data["spd_lvl"])
        if "maintenance_interval_hours" in data:
            p.maintenance_interval_hours = int(data["maintenance_interval_hours"])
        if data.get("reset_maintenance") is True:
            p.maintenance_hours_counter = 0.0

        if reconnect_mqtt:
            p.destroy()
            p.init_mqtt(asyncio.get_running_loop())

        await app_obj.save_printers_config()
        logger.info(f"⚙️ Updated per-printer settings for [{p.name}] via REST API")
        return web.json_response(
            {
                "status": "ok",
                "settings": {
                    "id": p.id,
                    "name": p.name,
                    "ip": p.ip,
                    "accessCode": p.access_code,
                    "serialNumber": p.serial_number,
                    "printer_model": getattr(p, "printer_model", "A1"),
                    "ams_enabled": getattr(p, "ams_enabled", None),
                    "notify": p.notify,
                    "spd_lvl": getattr(p, "spd_lvl", 2),
                    "maintenance_interval_hours": getattr(p, "maintenance_interval_hours", 100),
                    "maintenance_hours_counter": round(getattr(p, "maintenance_hours_counter", 0.0), 1),
                },
            }
        )
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)
