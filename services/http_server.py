"""
Lightweight REST API & WebApp HTTP server for 3D Printer Farm.
Uses aiohttp.web running inside the main asyncio event loop.
"""
import uuid
import time
import json
import asyncio
from pathlib import Path
import re
import hmac
import hashlib
import urllib.parse
from typing import Any, Optional
from aiohttp import web
from config import logger, HTTP_PORT, API_SECRET_KEY, STORAGE_DIR, TELEGRAM_BOT_TOKEN
from services.camera_stream import capture_real_camera_photo
from services.gcode_parser import parse_3mf_file, check_compatibility
from models.commercial import calculate_commercial_price
from models.printer import BambuPrinter

START_TIME = time.time()
WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
PRESETS_FILE = STORAGE_DIR / "commercial_presets.json"

# IP Rate Limiting storage: ip -> list of request timestamps
IP_REQUEST_LOGS: dict[str, list[float]] = {}
MAX_REQ_PER_MINUTE = 120
MAX_UPLOADS_PER_MINUTE = 10

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

def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """
    Cryptographically verifies Telegram WebApp initData HMAC-SHA256 signature.
    Returns parsed user dict if valid, or None if invalid/tampered.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(calculated_hash, hash_val):
            user_raw = parsed.get("user")
            if user_raw:
                return json.loads(user_raw)
            return {"valid": True}
    except Exception as e:
        logger.warning(f"Telegram initData verification error: {e}")
    return None

async def check_auth(request: web.Request) -> bool:
    """
    Multi-layer Security Check with strict Team Authorization:
    1. Validates X-API-Key header or ?token= query parameter against API_SECRET_KEY.
    2. Validates X-Telegram-Init-Data header or ?initData= query parameter HMAC signature against TELEGRAM_BOT_TOKEN
       AND checks if the Telegram user is an APPROVED team member in DB (is_user_approved).
    3. Denies access to unapproved, deleted, or unauthenticated external requests.
    """
    app_obj = request.app.get("app_obj")

    # 1. Check API Key for server-to-server / webhook integrations
    req_key = request.headers.get("X-API-Key") or request.query.get("token", "")
    if API_SECRET_KEY and req_key == API_SECRET_KEY:
        return True

    # 2. Check Telegram WebApp initData HMAC + DB User Approval
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("initData", "")
    if init_data:
        t_user = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
        if t_user and isinstance(t_user, dict):
            u_id = str(t_user.get("id") or "")
            if u_id and app_obj and hasattr(app_obj, "is_user_approved"):
                is_approved = await app_obj.is_user_approved(u_id)
                if not is_approved:
                    logger.warning(f"⛔ Revoked/unapproved user [{u_id}] attempted WebApp access!")
                    return False
                return True
            elif t_user.get("valid"):
                return True
        logger.warning("⛔ Invalid/tampered Telegram initData signature received!")
        return False

    # 3. Allow direct local unit test requests (aiohttp AioHTTPTestCase test client without tunnel)
    is_tunnel_req = bool(request.headers.get("X-Forwarded-For") or request.headers.get("X-Forwarded-Host") or request.headers.get("Bypass-Tunnel-Reminder"))
    if not API_SECRET_KEY and not is_tunnel_req and request.remote in ("127.0.0.1", "::1", None):
        return True

    return False

@web.middleware
async def security_and_ratelimit_middleware(request: web.Request, handler) -> web.StreamResponse:
    client_ip = request.remote or "127.0.0.1"
    now = time.time()

    # Clean up old timestamps (> 60s)
    timestamps = [t for t in IP_REQUEST_LOGS.get(client_ip, []) if now - t < 60.0]

    # Check upload limit vs general limit
    limit = MAX_UPLOADS_PER_MINUTE if request.path == "/api/files/upload" else MAX_REQ_PER_MINUTE
    if len(timestamps) >= limit:
        logger.warning(f"⛔ Rate limit exceeded for IP [{client_ip}] on {request.path}")
        return web.json_response(
            {"error": "Too Many Requests", "message": "Rate limit exceeded. Please wait 60 seconds."},
            status=429
        )

    timestamps.append(now)
    IP_REQUEST_LOGS[client_ip] = timestamps

    # Process request
    response = await handler(request)

    # Apply HTTP Security & Cache-Control Headers
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "ALLOW-FROM https://web.telegram.org"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:;"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

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
        "ams_trays_info": getattr(p, "ams_trays_info", {}),
        "active_ams_tray": getattr(p, "active_ams_tray", 255),
        "active_slot_key": p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "255",
        "has_ams": p.has_ams if hasattr(p, "has_ams") else bool(getattr(p, "ams_units", [])),
        "notify": getattr(p, "notify", True)
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

        if not name or not ip or not access_code or not serial_number:
            return web.json_response({"error": "Всі поля (Назва, IP, Access Code, SN) обов'язкові!"}, status=400)

        p_data = {
            "id": str(uuid.uuid4()),
            "name": name,
            "ip": ip,
            "accessCode": access_code,
            "serialNumber": serial_number,
            "filament_grams": float(data.get("filament_grams", 1000.0)),
            "notify": True
        }

        p_obj = BambuPrinter(p_data, app_obj.storage, save_callback=app_obj.save_printers_config)
        p_obj.init_mqtt()
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
        return web.json_response({"status": "ok", "action": "set_maint_interval", "item_key": item_key, "interval_hours": interval})
    elif action == "set_filament":
        grams = float(data.get("grams", 1000.0))
        slot_id = data.get("slot_id")
        p.set_slot_grams(grams, slot_id=slot_id)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "set_filament", "grams": grams, "slot_id": slot_id})
    elif action == "assign_spool":
        spool_id = str(data.get("spool_id", ""))
        slot_id = str(data.get("slot_id") or "255")
        spools = await app_obj.storage.load_spools()
        spool = spools.get(spool_id)
        if not spool:
            return web.json_response({"error": "Котушку не знайдено на складі"}, status=404)

        grams = float(spool.get("remaining_grams", 1000.0))
        p.set_slot_grams(grams, slot_id=slot_id)
        p.active_spool_id = spool_id
        if spool.get("type"):
            p.filament_type = str(spool.get("type"))
        if spool.get("price_per_kg") or spool.get("price_uah"):
            p.price_per_kg = float(spool.get("price_per_kg") or spool.get("price_uah"))

        spool["assigned_printer_id"] = p.id
        spool["assigned_slot_key"] = slot_id
        spools[spool_id] = spool
        await app_obj.storage.save_spools(spools)
        await app_obj.save_printers_config()
        return web.json_response({"status": "ok", "action": "assign_spool", "spool": spool, "slot_id": slot_id})
    elif action == "unassign_spool":
        slot_id = str(data.get("slot_id") or "255")
        spools = await app_obj.storage.load_spools()
        for s_id, s in spools.items():
            if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == slot_id:
                s["assigned_printer_id"] = None
                s["assigned_slot_key"] = None
                spools[s_id] = s
        await app_obj.storage.save_spools(spools)
        return web.json_response({"status": "ok", "action": "unassign_spool", "slot_id": slot_id})
    elif action == "set_ams_enabled":
        enabled = bool(data.get("enabled", False))
        p.ams_enabled = enabled
        await app_obj.save_printers_config()
        logger.info(f"⚙️ Set ams_enabled={enabled} for [{p.name}]")
        return web.json_response({"status": "ok", "action": "set_ams_enabled", "enabled": enabled, "has_ams": p.has_ams})
    elif action == "calibrate":
        if p.gcode_state == "RUNNING":
            return web.json_response({"error": "Неможливо запустити калібрування під час друку!"}, status=400)
        ok = p.start_calibration()
        if ok:
            return web.json_response({"status": "ok", "action": "calibrate", "message": "Запущено авто-калібрування!"})
        else:
            return web.json_response({"error": "Не вдалося запустити калібрування (перевірте MQTT з'єднання)"}, status=500)
    else:
        return web.json_response({"error": f"Unknown action '{action}'"}, status=400)

async def handle_file_upload(request: web.Request) -> web.Response:
    """POST /api/files/upload - Accepts 3MF / GCode upload and parses metadata."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or not field.filename:
            return web.json_response({"error": "No file provided"}, status=400)

        # Sanitize filename & prevent path traversal
        raw_name = Path(field.filename).name
        clean_ext = ".3mf" if raw_name.lower().endswith(".3mf") else ".gcode" if raw_name.lower().endswith(".gcode") else ""
        if not clean_ext:
            return web.json_response({"error": "Дозволено завантажувати тільки файли .3mf або .gcode"}, status=400)

        clean_base = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name.rsplit('.', 1)[0])
        safe_filename = f"{clean_base}{clean_ext}"

        content_buf = bytearray()
        max_bytes = 50 * 1024 * 1024
        while True:
            chunk = await field.read_chunk(size=1024 * 1024)
            if not chunk:
                break
            content_buf.extend(chunk)
            if len(content_buf) > max_bytes:
                return web.json_response({"error": "Файл перевищує максимальний дозволений розмір 50 MB"}, status=413)

        content = bytes(content_buf)

        # Validate .3mf ZIP magic bytes
        if clean_ext == ".3mf" and not content.startswith(b"PK\x03\x04"):
            return web.json_response({"error": "Недійсний підпис .3mf файлу"}, status=400)

        meta = parse_3mf_file(content, safe_filename)
        if not meta.get("valid"):
            return web.json_response({"error": meta.get("error", "Недійсний файл .3mf")}, status=400)

        upload_dir = STORAGE_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_token = f"{int(time.time())}_{safe_filename}"
        save_path = (upload_dir / file_token).resolve()
        if upload_dir.resolve() not in save_path.parents:
            return web.json_response({"error": "Illegal file path"}, status=400)

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
    if not await check_auth(request):
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
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    return web.json_response(spools)

async def handle_save_spool(request: web.Request) -> web.Response:
    """POST /api/spools - Add or update a spool."""
    if not await check_auth(request):
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
    if not await check_auth(request):
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
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    presets = await load_commercial_presets(app_obj)
    return web.json_response(presets)

async def handle_save_preset(request: web.Request) -> web.Response:
    """POST /api/commercial/presets - Create or update commercial preset."""
    if not await check_auth(request):
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
    if not await check_auth(request):
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
    if not await check_auth(request):
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
    if not await check_auth(request):
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

async def handle_export_history_csv(request: web.Request) -> web.Response:
    """GET /api/history/export - Exports completed print jobs history as CSV file."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    history = await app_obj.storage.load_json(app_obj.storage.history_file, [])

    csv_lines = ["Дата,Принтер,Модель,Вага (г),Матеріал,Собівартість (грн)"]
    for item in history:
        ts = item.get("timestamp", 0)
        dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "-"
        pname = str(item.get("printer_name", "")).replace(",", " ")
        mname = str(item.get("subtask_name", "")).replace(",", " ")
        weight = item.get("weight_g", 0.0)
        ftype = str(item.get("filament_type", "")).replace(",", " ")
        cost = item.get("cost_uah", 0.0)
        csv_lines.append(f'"{dt_str}","{pname}","{mname}",{weight},"{ftype}",{cost}')

    csv_body = "\n".join(csv_lines)
    filename = f"farm_history_{int(time.time())}.csv"
    return web.Response(
        body=csv_body.encode("utf-8-sig"),
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

async def handle_events_sse(request: web.Request) -> web.StreamResponse:
    """GET /api/events - Server-Sent Events (SSE) streaming live telemetry to WebApp."""
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)
    app_obj = request.app["app_obj"]

    try:
        while True:
            printers_list = [build_printer_telemetry(p) for p in app_obj.printers.values()]
            data_json = json.dumps(printers_list)
            sse_msg = f"data: {data_json}\n\n"
            await response.write(sse_msg.encode('utf-8'))
            await asyncio.sleep(2.5)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    return response

async def handle_get_settings(request: web.Request) -> web.Response:
    """GET /api/settings - Global settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    settings = await app_obj.storage.load_json(app_obj.storage.settings_file, app_obj.global_settings)
    return web.json_response(settings)

async def handle_update_settings(request: web.Request) -> web.Response:
    """POST /api/settings - Save global settings."""
    if not await check_auth(request):
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
    """Creates aiohttp web Application with configured API routes, security middlewares & static WebApp assets."""
    web_app = web.Application(
        client_max_size=50 * 1024 * 1024,
        middlewares=[security_and_ratelimit_middleware]
    )
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
    web_app.router.add_post("/api/printers", handle_create_printer)
    web_app.router.add_delete("/api/printers/{id}", handle_delete_printer)
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

    web_app.router.add_get("/api/events", handle_events_sse)
    web_app.router.add_get("/api/history", handle_get_history)
    web_app.router.add_get("/api/history/export", handle_export_history_csv)
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
