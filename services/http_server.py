"""
Lightweight REST API & WebApp HTTP server for 3D Printer Farm.
Uses aiohttp.web running inside the main asyncio event loop.
"""
import time
import json
import asyncio
from pathlib import Path
from typing import Any
from aiohttp import web
from config import logger, HTTP_PORT, API_SECRET_KEY, STORAGE_DIR
from services.camera_stream import capture_real_camera_photo
from services.gcode_parser import parse_3mf_file, check_compatibility
from models.commercial import calculate_commercial_price

START_TIME = time.time()
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
PRESETS_FILE = STORAGE_DIR / "commercial_presets.json"

DEFAULT_PRESETS = {
    "default_pla": {
        "id": "default_pla",
        "name": "Стандарт PLA (850 грн/кг, +100%)",
        "price_per_g": 0.85,
        "electricity_rate_uah": 4.32,
        "power_watts": 120.0,
        "depreciation_val": "10",
        "consumables_val": "5",
        "profit_val": "100%"
    },
    "default_petg": {
        "id": "default_petg",
        "name": "PETG / Engineering (950 грн/кг, +100%)",
        "price_per_g": 0.95,
        "electricity_rate_uah": 4.32,
        "power_watts": 150.0,
        "depreciation_val": "15",
        "consumables_val": "8",
        "profit_val": "100%"
    }
}

def check_auth(request: web.Request) -> bool:
    """Validates X-API-Key header or ?token= query parameter if API_SECRET_KEY is configured."""
    if not API_SECRET_KEY:
        return True
    req_key = request.headers.get("X-API-Key") or request.query.get("token", "")
    return req_key == API_SECRET_KEY

async def handle_serve_index(request: web.Request) -> web.FileResponse:
    """Serves the main Telegram WebApp single-page application."""
    index_file = WEBAPP_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="<h1>WebApp index.html not found</h1>", content_type="text/html", status=404)
    return web.FileResponse(index_file)

async def handle_health(request: web.Request) -> web.Response:
    """GET /health - System health check endpoint for UptimeRobot / Docker / systemd."""
    app_obj = request.app["app_obj"]
    uptime = int(time.time() - START_TIME)
    printers = list(app_obj.printers.values())
    active = sum(1 for p in printers if p.gcode_state == "RUNNING")

    return web.json_response({
        "status": "ok",
        "uptime_seconds": uptime,
        "total_printers": len(printers),
        "active_printers": active
    })

def build_printer_telemetry(p: Any) -> dict:
    used_w = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
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
        "filament_grams_left": p.filament_grams,
        "job_weight_g": round(used_w, 2),
        "chamber_light_state": getattr(p, "chamber_light_state", "off"),
        "spd_lvl": getattr(p, "spd_lvl", 2),
        "spd_mag": getattr(p, "spd_mag", 100),
        "maintenance_hours_counter": round(getattr(p, "maintenance_hours_counter", 0.0), 1),
        "maintenance_interval_hours": getattr(p, "maintenance_interval_hours", 100),
        "total_print_hours": round(getattr(p, "total_print_hours", 0.0), 1),
        "hms_errors": getattr(p, "hms_errors", []),
        "ams_slots": getattr(p, "ams_slots", {}),
        "active_ams_tray": getattr(p, "active_ams_tray", 255),
        "active_slot_key": p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "255",
        "notify": getattr(p, "notify", True)
    }

async def handle_get_printers(request: web.Request) -> web.Response:
    """GET /api/printers - Live telemetry array for WebApp / HA / Grafana."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    result = [build_printer_telemetry(p) for p in app_obj.printers.values()]
    return web.json_response(result)

async def handle_get_printer_by_id(request: web.Request) -> web.Response:
    """GET /api/printers/{id} - Single printer telemetry."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    return web.json_response(build_printer_telemetry(p))

async def handle_get_snapshot(request: web.Request) -> web.Response:
    """GET /api/printers/{id}/snapshot - Live JPEG frame for WebApp / Home Assistant."""
    if not check_auth(request):
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

async def handle_printer_control(request: web.Request) -> web.Response:
    """POST /api/printers/{id}/control - Remote actions."""
    if not check_auth(request):
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
        p.pause_print()
        return web.json_response({"status": "ok", "action": "pause"})
    elif action == "resume":
        p.resume_print()
        return web.json_response({"status": "ok", "action": "resume"})
    elif action == "stop":
        p.stop_print()
        return web.json_response({"status": "ok", "action": "stop"})
    elif action == "light_toggle":
        new_s = "off" if p.chamber_light_state == "on" else "on"
        p.set_chamber_light(new_s)
        return web.json_response({"status": "ok", "action": "light_toggle", "state": new_s})
    elif action == "set_speed":
        level = int(data.get("level", 2))
        p.set_print_speed(level)
        return web.json_response({"status": "ok", "action": "set_speed", "level": level})
    elif action == "reset_maint":
        p.maintenance_hours_counter = 0.0
        p.last_maintenance_timestamp = time.time()
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "reset_maint"})
    elif action == "set_filament":
        grams = float(data.get("grams", 1000.0))
        slot_id = data.get("slot_id")
        p.set_slot_grams(grams, slot_id=slot_id)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "set_filament", "grams": grams, "slot_id": slot_id})
    else:
        return web.json_response({"error": f"Unknown action '{action}'"}, status=400)

async def handle_file_upload(request: web.Request) -> web.Response:
    """POST /api/files/upload - Accepts 3MF / GCode upload and parses metadata."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or not field.filename:
            return web.json_response({"error": "No file provided"}, status=400)

        filename = field.filename
        content_buf = bytearray()
        while True:
            chunk = await field.read_chunk(size=1024 * 1024)
            if not chunk:
                break
            content_buf.extend(chunk)
        content = bytes(content_buf)

        meta = parse_3mf_file(content, filename)
        if not meta.get("valid"):
            return web.json_response({"error": meta.get("error", "Недійсний файл .3mf")}, status=400)

        upload_dir = STORAGE_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_token = f"{int(time.time())}_{filename}"
        save_path = upload_dir / file_token
        save_path.write_bytes(content)

        printers_info = []
        for p_id, p in app_obj.printers.items():
            comp = check_compatibility(meta["printer_model"], meta["filament_type"], p.name)
            printers_info.append({
                "id": p.id,
                "name": p.name,
                "state": p.gcode_state,
                "compatible": comp["compatible"],
                "reason": comp.get("reason", "")
            })

        return web.json_response({
            "status": "ok",
            "file_token": file_token,
            "filename": filename,
            "printer_model": meta["printer_model"],
            "filament_type": meta["filament_type"],
            "weight_g": meta["weight_g"],
            "time_mins": meta["time_mins"],
            "printers": printers_info
        })
    except Exception as e:
        logger.error(f"Error handling WebApp file upload: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_start_print_job(request: web.Request) -> web.Response:
    """POST /api/printers/{id}/print_file - Uploads file via FTPS to printer and starts print."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    p = app_obj.printers.get(p_id)
    if not p:
        return web.json_response({"error": "Printer not found"}, status=404)

    try:
        data = await request.json()
        file_token = data.get("file_token", "")
        save_path = STORAGE_DIR / "uploads" / file_token
        if not save_path.exists():
            return web.json_response({"error": "Uploaded file not found"}, status=404)

        file_bytes = save_path.read_bytes()
        filename = data.get("filename") or file_token.split("_", 1)[-1]

        ok, msg = await p.start_print_job_async(file_bytes, filename)
        if ok:
            return web.json_response({"status": "ok", "message": msg})
        else:
            return web.json_response({"error": msg}, status=500)
    except Exception as e:
        logger.error(f"Error starting print job from WebApp: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def handle_get_spools(request: web.Request) -> web.Response:
    """GET /api/spools - Filament spool inventory."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    return web.json_response(spools)

async def handle_save_spool(request: web.Request) -> web.Response:
    """POST /api/spools - Add or update a spool."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        spool_id = data.get("id") or f"spool_{int(time.time())}"
        spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
        spools[spool_id] = {
            "id": spool_id,
            "name": data.get("name", "Котушка"),
            "type": data.get("type", "PLA"),
            "color": data.get("color", "#ffffff"),
            "remaining_grams": float(data.get("remaining_grams", 1000.0)),
            "price_per_kg": float(data.get("price_per_kg", 650.0)),
            "notes": data.get("notes", "")
        }
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)
        return web.json_response({"status": "ok", "spool": spools[spool_id]})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def handle_delete_spool(request: web.Request) -> web.Response:
    """DELETE /api/spools/{id} - Remove a spool from inventory."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id = request.match_info.get("id", "")
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    if spool_id in spools:
        del spools[spool_id]
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Spool not found"}, status=404)

async def load_commercial_presets(app_obj: Any) -> dict:
    presets = await app_obj.storage.load_json(PRESETS_FILE, {})
    if not presets:
        presets = DEFAULT_PRESETS.copy()
        await app_obj.storage.save_json(PRESETS_FILE, presets)
    return presets

async def handle_get_presets(request: web.Request) -> web.Response:
    """GET /api/commercial/presets - List commercial pricing presets."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    presets = await load_commercial_presets(app_obj)
    return web.json_response(presets)

async def handle_save_preset(request: web.Request) -> web.Response:
    """POST /api/commercial/presets - Create or update commercial preset."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        p_id = data.get("id") or f"preset_{int(time.time())}"
        
        raw_price = data.get("price_per_g")
        try:
            price_g = float(raw_price) if raw_price is not None else 0.85
        except (ValueError, TypeError):
            price_g = 0.85

        raw_elec = data.get("electricity_rate_uah")
        try:
            elec_rate = float(raw_elec) if raw_elec is not None else 4.32
        except (ValueError, TypeError):
            elec_rate = 4.32

        raw_power = data.get("power_watts")
        try:
            power_w = float(raw_power) if raw_power is not None else 120.0
        except (ValueError, TypeError):
            power_w = 120.0

        presets = await load_commercial_presets(app_obj)
        presets[p_id] = {
            "id": p_id,
            "name": str(data.get("name") or "Новий пресет"),
            "price_per_g": price_g,
            "electricity_rate_uah": elec_rate,
            "power_watts": power_w,
            "depreciation_val": str(data.get("depreciation_val") or "10"),
            "consumables_val": str(data.get("consumables_val") or "5"),
            "profit_val": str(data.get("profit_val") or "100%")
        }
        await app_obj.storage.save_json(PRESETS_FILE, presets)
        return web.json_response({"status": "ok", "preset": presets[p_id]})
    except Exception as e:
        logger.error(f"Error saving commercial preset: {e}")
        return web.json_response({"error": str(e)}, status=400)

async def handle_delete_preset(request: web.Request) -> web.Response:
    """DELETE /api/commercial/presets/{id} - Remove commercial preset."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    presets = await load_commercial_presets(app_obj)
    if p_id in presets:
        del presets[p_id]
        await app_obj.storage.save_json(PRESETS_FILE, presets)
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Preset not found"}, status=404)

async def handle_calculate_commercial(request: web.Request) -> web.Response:
    """POST /api/commercial/calculate - Calculate pricing breakdown."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        weight_g = float(data.get("weight_g", 100.0))
        time_mins = int(data.get("time_mins", 60))
        preset_id = data.get("preset_id")

        presets = await load_commercial_presets(app_obj)
        preset = presets.get(preset_id) if preset_id else data.get("preset")
        if not preset:
            preset = list(presets.values())[0] if presets else DEFAULT_PRESETS["default_pla"]

        calc = calculate_commercial_price(preset, weight_g, time_mins)
        return web.json_response({"status": "ok", "calculation": calc})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def handle_get_history(request: web.Request) -> web.Response:
    """GET /api/history - Completed print jobs history."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    history = await app_obj.storage.load_json(app_obj.storage.history_file, [])
    total_grams = sum(item.get("weight_g", 0.0) for item in history)
    total_cost = sum(item.get("cost_uah", 0.0) for item in history)

    return web.json_response({
        "total_jobs": len(history),
        "total_weight_kg": round(total_grams / 1000.0, 2),
        "total_cost_uah": round(total_cost, 2),
        "history": history
    })

async def handle_get_settings(request: web.Request) -> web.Response:
    """GET /api/settings - Global settings."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    settings = await app_obj.storage.load_json(app_obj.storage.settings_file, app_obj.global_settings)
    return web.json_response(settings)

async def handle_update_settings(request: web.Request) -> web.Response:
    """POST /api/settings - Save global settings."""
    if not check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        app_obj.global_settings.update(data)
        await app_obj.storage.save_json(app_obj.storage.settings_file, app_obj.global_settings)
        return web.json_response({"status": "ok", "settings": app_obj.global_settings})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

def create_http_app(app_obj: Any) -> web.Application:
    """Creates aiohttp web Application with configured API routes & static WebApp assets."""
    web_app = web.Application(client_max_size=100 * 1024 * 1024)
    web_app["app_obj"] = app_obj

    # WebApp Index & Assets
    web_app.router.add_get("/", handle_serve_index)
    web_app.router.add_get("/webapp", handle_serve_index)

    static_dir = WEBAPP_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    web_app.router.add_static("/static/", path=str(static_dir), name="static")

    # API Endpoints
    web_app.router.add_get("/health", handle_health)
    web_app.router.add_get("/api/printers", handle_get_printers)
    web_app.router.add_get("/api/printers/{id}", handle_get_printer_by_id)
    web_app.router.add_get("/api/printers/{id}/snapshot", handle_get_snapshot)
    web_app.router.add_post("/api/printers/{id}/control", handle_printer_control)

    # File Upload & Print Job API
    web_app.router.add_post("/api/files/upload", handle_file_upload)
    web_app.router.add_post("/api/printers/{id}/print_file", handle_start_print_job)

    web_app.router.add_get("/api/spools", handle_get_spools)
    web_app.router.add_post("/api/spools", handle_save_spool)
    web_app.router.add_delete("/api/spools/{id}", handle_delete_spool)

    # Commercial Pricing API
    web_app.router.add_get("/api/commercial/presets", handle_get_presets)
    web_app.router.add_post("/api/commercial/presets", handle_save_preset)
    web_app.router.add_delete("/api/commercial/presets/{id}", handle_delete_preset)
    web_app.router.add_post("/api/commercial/calculate", handle_calculate_commercial)

    web_app.router.add_get("/api/history", handle_get_history)
    web_app.router.add_get("/api/settings", handle_get_settings)
    web_app.router.add_post("/api/settings", handle_update_settings)

    return web_app

async def start_http_server(app_obj: Any, host: str = "0.0.0.0", port: int = HTTP_PORT):
    """Starts async HTTP REST API server on specified port."""
    web_app = create_http_app(app_obj)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"🌐 [WebApp & REST API] Server started at http://{host}:{port} (WebApp: http://{host}:{port}/webapp)")
