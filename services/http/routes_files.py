"""
File upload and 3MF / GCode print job execution endpoints.
"""

import gc
import re
import time
from pathlib import Path
from typing import Any

from aiohttp import web

import config
from config import logger
from services.gcode_parser import check_compatibility, get_printer_active_filament, parse_3mf_file
from services.http.auth import check_auth


async def handle_file_upload(request: web.Request) -> web.Response:
    """POST /api/files/upload - Accepts 3MF / GCode upload and parses metadata."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        reader = await request.multipart()
        field: Any = await reader.next()
        if not field or not getattr(field, "filename", None):
            return web.json_response({"error": "No file provided"}, status=400)

        # Sanitize filename & prevent path traversal
        raw_name = Path(field.filename).name
        clean_ext = (
            ".3mf" if raw_name.lower().endswith(".3mf") else ".gcode" if raw_name.lower().endswith(".gcode") else ""
        )
        if not clean_ext:
            return web.json_response({"error": "Дозволено завантажувати тільки файли .3mf або .gcode"}, status=400)

        clean_base = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.rsplit(".", 1)[0])
        safe_filename = f"{clean_base}{clean_ext}"

        upload_dir = config.STORAGE_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_token = f"{int(time.time())}_{safe_filename}"
        save_path = (upload_dir / file_token).resolve()

        if upload_dir.resolve() not in save_path.parents:
            return web.json_response({"error": "Illegal file path"}, status=400)

        max_bytes = 50 * 1024 * 1024
        total_bytes = 0
        first_chunk = None

        with save_path.open("wb") as out_f:
            while True:
                chunk = await field.read_chunk(size=256 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    out_f.close()
                    save_path.unlink(missing_ok=True)
                    return web.json_response(
                        {"error": "Файл перевищує максимальний дозволений розмір 50 MB"}, status=413
                    )
                if first_chunk is None:
                    first_chunk = chunk
                out_f.write(chunk)

        # Validate .3mf ZIP magic bytes on first chunk
        if clean_ext == ".3mf" and first_chunk and not first_chunk.startswith(b"PK\x03\x04"):
            save_path.unlink(missing_ok=True)
            return web.json_response({"error": "Недійсний підпис .3mf файлу"}, status=400)

        content = save_path.read_bytes()
        meta = parse_3mf_file(content, safe_filename)
        del content
        gc.collect()

        if not meta.get("valid"):
            save_path.unlink(missing_ok=True)
            return web.json_response({"error": meta.get("error", "Недійсний файл .3mf")}, status=400)

        spools_map = await app_obj.storage.load_spools()
        printers_info = []
        for p_id, p in app_obj.printers.items():
            active_fil = get_printer_active_filament(p, spools_map)
            comp = check_compatibility(meta["printer_model"], meta["filament_type"], p.name, active_fil)
            printers_info.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "state": p.gcode_state,
                    "compatible": comp["compatible"],
                    "reason_type": comp.get("reason_type", "OK"),
                    "reason": comp.get("reason", ""),
                }
            )

        return web.json_response(
            {
                "status": "ok",
                "file_token": file_token,
                "filename": safe_filename,
                "printer_model": meta["printer_model"],
                "filament_type": meta["filament_type"],
                "weight_g": meta["weight_g"],
                "time_mins": meta["time_mins"],
                "printers": printers_info,
            }
        )
    except Exception as e:
        logger.error(f"Error handling WebApp file upload: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_image_upload(request: web.Request) -> web.Response:
    """POST /api/files/upload_image - Accepts image file upload from WebApp with auto-compression."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB DoS limit

    if request.content_length and request.content_length > MAX_UPLOAD_BYTES:
        return web.json_response({"error": "Файл занадто великий"}, status=413)

    try:
        reader = await request.multipart()
        field: Any = await reader.next()
        if not field or not getattr(field, "filename", None):
            return web.json_response({"error": "No file provided"}, status=400)

        raw_name = Path(field.filename).name
        ext = Path(raw_name).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return web.json_response({"error": "Підтримуються лише зображення (.jpg, .png, .webp, .gif)"}, status=400)

        raw_bytes = bytearray()
        while True:
            chunk = await field.read_chunk(size=256 * 1024)
            if not chunk:
                break
            raw_bytes.extend(chunk)
            if len(raw_bytes) > MAX_UPLOAD_BYTES:
                return web.json_response({"error": "Файл занадто великий"}, status=413)

        from utils.image_utils import compress_part_photo
        try:
            compressed = compress_part_photo(bytes(raw_bytes))
        except Exception as img_err:
            logger.warning(f"Failed compressing image: {img_err}")
            return web.json_response({"error": "Не вдалося обробити зображення"}, status=400)

        clean_base = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.rsplit(".", 1)[0])
        file_token = f"img_{int(time.time())}_{clean_base}.jpg"

        upload_dir = config.STORAGE_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = upload_dir / file_token

        save_path.write_bytes(compressed)

        image_url = f"/uploads/{file_token}"
        return web.json_response({"status": "ok", "image_url": image_url, "file_token": file_token})
    except Exception as e:
        logger.error(f"Error handling image upload: {e}")
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
        save_path = config.STORAGE_DIR / "uploads" / file_token
        if not save_path.exists():
            return web.json_response({"error": "Uploaded file not found"}, status=404)

        file_bytes = save_path.read_bytes()
        filename = data.get("filename") or file_token.split("_", 1)[-1]

        # Parse 3MF / Gcode metadata for current job weight & plate_name
        meta = parse_3mf_file(file_bytes, filename)
        job_w = float(meta.get("weight_g", 0.0))
        plate_name = meta.get("plate_name", "plate_1.gcode")

        # Strict Hardware & Filament Compatibility Validation
        from services.gcode_parser import check_compatibility, get_printer_active_filament
        spools = await app_obj.storage.load_spools() if (app_obj and hasattr(app_obj, "storage") and hasattr(app_obj.storage, "load_spools")) else {}
        active_fil = get_printer_active_filament(p, spools)

        comp = check_compatibility(
            sliced_model=meta.get("printer_model", ""),
            filament_type=meta.get("filament_type", ""),
            target_printer_name=p.name,
            target_filament=active_fil,
        )
        if not comp.get("compatible"):
            reason = comp.get("reason", "🛑 Несумісний принтер або пластик!")
            logger.warning(f"⛔ Blocked incompatible uploaded file print on '{p.name}': {reason}")
            return web.json_response({"error": f"🛑 Друк заблоковано: {reason}"}, status=400)

        ok, msg = await p.start_print_job_async(file_bytes, filename, plate_name=plate_name)
        if ok:
            p._is_printing = True
            p._was_running = True
            p._job_started_from_app = True
            p._history_recorded = False
            p._job_deducted = False
            if job_w > 0:
                p._current_job_grams = job_w
                try:
                    import json
                    cache_file = config.STORAGE_DIR / "last_sliced_weight.json"
                    cache_payload = {
                        "filename": filename,
                        "weight": job_w,
                        "timestamp": time.time(),
                    }
                    cache_file.write_text(json.dumps(cache_payload), encoding="utf-8")
                except Exception as cache_err:
                    logger.warning(f"Failed writing weight cache: {cache_err}")

            return web.json_response({"status": "ok", "message": msg})
        else:
            return web.json_response({"error": msg}, status=500)
    except Exception as e:
        logger.error(f"Error starting print job from WebApp: {e}")
        return web.json_response({"error": str(e)}, status=500)
