"""
File upload and 3MF / GCode print job execution endpoints.
"""

import gc
import re
import time
from pathlib import Path
from typing import Any

from aiohttp import web

from config import STORAGE_DIR, logger
from services.gcode_parser import check_compatibility, parse_3mf_file
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

        upload_dir = STORAGE_DIR / "uploads"
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

        printers_info = []
        for p_id, p in app_obj.printers.items():
            comp = check_compatibility(meta["printer_model"], meta["filament_type"], p.name)
            printers_info.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "state": p.gcode_state,
                    "compatible": comp["compatible"],
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
