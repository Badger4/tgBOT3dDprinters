"""
Service for handling 3D print file operations, FTPS transfers, 3MF parsing, plate previews,
and MQTT project_file job dispatching for Bambu Lab printers.
Decoupled from models/printer.py to adhere to the Single Responsibility Principle (SRP).
"""
import asyncio
import hashlib
import html
import io
import json
import logging
import re
import sys
import time
import zipfile
from typing import Any

from config import STORAGE_DIR
from models.enums import AMSSlot
from services.ftps_client import (
    fetch_bambu_ftps_info,
    upload_3mf_to_bambu,
    verify_bambu_file_size,
)
from services.gcode_parser import parse_3mf_file
from utils.image_utils import render_plate_gif

logger = logging.getLogger(__name__)


def _get_printer_dep(name: str, fallback: Any) -> Any:
    """Safely retrieves patched dependencies from models.printer if present in sys.modules."""
    try:
        mod = sys.modules.get("models.printer")
        if mod and hasattr(mod, name):
            return getattr(mod, name)
    except Exception:
        pass
    return fallback


def fetch_job_info_via_ftps(printer: Any) -> None:
    """
    Safely initiates background FTPS retrieval of model weight and printable objects metadata.
    Avoids blocking MQTT thread or event loop.
    """
    if getattr(printer, "_ftps_fetching", False) or not printer.ip or not printer.access_code:
        return
    loop_to_use = printer._get_active_event_loop()
    if not loop_to_use or not loop_to_use.is_running():
        return
    printer._ftps_fetching = True

    fetch_fn = _get_printer_dep("fetch_bambu_ftps_info", fetch_bambu_ftps_info)

    def _worker() -> None:
        try:
            if printer.ip and printer.access_code:
                info = fetch_fn(printer.ip, printer.access_code, printer.subtask_name)
                w = float(info.get("weight_g") or 0.0)
                objs = info.get("objects") or []
                if objs:
                    printer.current_job_objects = objs
                    logger.info(
                        f"🧩 FTPS fetched {len(objs)} objects for [{printer.name}]: {[o.get('name') for o in objs]}"
                    )
                if w > 0:
                    printer._current_job_grams = w
                    logger.info(f"💡 FTPS fetched model weight {w}g for [{printer.name}]")
        except Exception as e:
            logger.warning(f"FTPS worker error for [{printer.name}]: {e}")
        finally:
            printer._ftps_fetching = False

    asyncio.run_coroutine_threadsafe(asyncio.to_thread(_worker), loop_to_use)


def render_plate_gif_cached(printer: Any) -> bytes:
    """
    Returns cached animated GIF of plate objects highlighting each object sequentially.
    Renders on demand if not already in cache.
    """
    if getattr(printer, "_plate_gif_cache", None) is None:
        p_model = str(getattr(printer, "printer_model", "") or getattr(printer, "name", "")).lower()
        bed_size = (180, 180) if "mini" in p_model else (256, 256)

        printer._plate_gif_cache = render_plate_gif(
            printer.get_clean_job_objects(),
            bed_size_mm=bed_size,
            skipped_ids=getattr(printer, "skipped_objects", []),
        )
    return printer._plate_gif_cache or b""


def invalidate_plate_gif_cache(printer: Any) -> None:
    """Clears cached animated GIF for plate map."""
    printer._plate_gif_cache = None


async def start_print_job(
    printer: Any,
    file_bytes: bytes,
    filename: str,
    plate_name: str = "plate_1.gcode",
    use_ams: bool = True,
    part_name: str | None = None,
    ams_slot: int | str | None = None,
    ams_mapping: list[int] | None = None,
    weight_g: float | None = None,
) -> tuple[bool, str]:
    """
    Uploads 3MF file via FTPS to printer SD card and publishes MQTT project_file command to start printing.
    Accepts selected physical AMS slot number (1-4) or explicit ams_mapping list [Virtual_T0..3].
    Returns (success: bool, user_message: str).
    """
    printer._current_job_slot_key = None

    if not printer._client or not printer._client.is_connected():
        return False, "⚠️ MQTT з'єднання з принтером відсутнє."

    upload_fn = _get_printer_dep("upload_3mf_to_bambu", upload_3mf_to_bambu)
    verify_fn = _get_printer_dep("verify_bambu_file_size", verify_bambu_file_size)
    parse_3mf_fn = _get_printer_dep("parse_3mf_file", parse_3mf_file)
    storage_dir = _get_printer_dep("STORAGE_DIR", STORAGE_DIR)

    from models.printer import build_ams_mapping as default_build_ams_mapping
    build_ams_mapping_fn = _get_printer_dep("build_ams_mapping", default_build_ams_mapping)

    # 1. Upload 3MF file to SD card via FTPS
    remote_path = await asyncio.to_thread(upload_fn, printer.ip, printer.access_code, file_bytes, filename)
    if not remote_path:
        return False, f"⚠️ Не вдалося завантажити файл по FTPS на {printer.name} (перевірте IP {printer.ip} та SD-карту)."

    # Verify file size on printer MicroSD card via FTPS SIZE command
    expected_size = len(file_bytes)
    verified = await asyncio.to_thread(verify_fn, printer.ip, printer.access_code, remote_path, expected_size)
    if not verified:
        logger.warning(
            f"⚠️ SD card size verification unconfirmed for {remote_path} on [{printer.name}]. Proceeding with job dispatch..."
        )

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

    printer.subtask_name = clean_subtask
    printer._custom_job_name = clean_subtask

    # Pre-calculate filament weight & extract plate objects from uploaded 3MF file
    m_info: dict[str, Any] = {}
    try:
        m_info = parse_3mf_fn(file_bytes, filename)
        printer.current_job_objects = m_info.get("objects", [])
        printer.skipped_objects = []
        w_g = float(m_info.get("weight_g") or 0.0)

        # Persist objects & weight into last_sliced_weight.json cache
        try:
            cache_file = storage_dir / "last_sliced_weight.json"
            cache_payload = {
                "filename": filename,
                "weight": w_g,
                "timestamp": time.time(),
                "objects": printer.current_job_objects,
            }
            cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False), encoding="utf-8")
            logger.info(f"🧩 Persisted {len(printer.current_job_objects)} objects to weight cache for [{printer.name}]")
        except Exception as e_cache:
            logger.warning(f"Failed writing weight/objects cache: {e_cache}")

        if w_g <= 0 and weight_g is not None and float(weight_g) > 0:
            w_g = float(weight_g)

        if w_g > 0:
            printer._current_job_grams = w_g
            printer._job_deducted = False
            logger.info(f"⚖️ Parsed 3MF weight {w_g}g for [{printer.name}]")
    except Exception as e_w:
        logger.warning(f"Could not parse 3MF weight in start_print_job: {e_w}")
        if weight_g is not None and float(weight_g) > 0:
            printer._current_job_grams = float(weight_g)
            printer._job_deducted = False

    has_ams_hardware = bool(getattr(printer, "has_ams", False))
    req_fil = str(m_info.get("filament_type") or "PLA").strip() if m_info else "PLA"
    target_slot = ams_slot

    # Automatic AMS slot detection if not explicitly passed
    if target_slot is None:
        if has_ams_hardware and use_ams:
            matched_idx = printer.find_matching_ams_slot(
                req_fil,
                tray_info_idx=m_info.get("tray_info_idx", ""),
                color=m_info.get("filament_color", ""),
                filament_name=m_info.get("filament_name", ""),
            )
            if matched_idx is not None:
                target_slot = matched_idx + 1  # 1-indexed physical slot (1-4)
                logger.info(
                    f"🎯 [AMS Auto-Select] Matched 3MF filament '{req_fil}' (tray_info_idx: {m_info.get('tray_info_idx', '')}, color: {m_info.get('filament_color', '')}) to physical Slot {target_slot} on [{printer.name}]"
                )
            else:
                ams_summary = printer.get_loaded_ams_summary()
                err_msg = (
                    f"⚠️ <b>Невідповідність філаменту в AMS!</b>\n"
                    f"Для файлу <code>{html.escape(filename)}</code> потрібен пластик <b>{html.escape(req_fil)}</b>, "
                    f"але в AMS принтера <b>{html.escape(printer.name)}</b> його не знайдено.\n\n"
                    f"📋 <b>Заправлені слоти:</b>\n{ams_summary}\n\n"
                    f"<i>Будь ласка, заправте {html.escape(req_fil)} в AMS або оберіть інший принтер.</i>"
                )
                logger.warning(f"AMS filament mismatch for [{printer.name}]: required '{req_fil}', slots: {ams_summary}")
                return False, err_msg
        else:
            target_slot = None
            use_ams = False

    # Resolve deduction slot key for accurate spool tracking
    deduct_key = None
    if target_slot is not None and str(target_slot).strip().upper() in ["254", "255", "VT", "EXTERNAL"]:
        deduct_key = AMSSlot.EXTERNAL.value
    elif target_slot is not None:
        ams_map, is_ams = build_ams_mapping_fn(target_slot, has_ams=has_ams_hardware, use_ams=use_ams)
        if is_ams and ams_map and ams_map[0] >= 0:
            deduct_key = str(ams_map[0])
        else:
            try:
                v = int(target_slot)
                if 1 <= v <= 4:
                    deduct_key = str(v - 1)
                elif v == 0:
                    deduct_key = "0"
            except (ValueError, TypeError):
                pass
    elif ams_mapping is not None and ams_mapping and ams_mapping[0] >= 0:
        deduct_key = str(ams_mapping[0])

    if deduct_key is None:
        deduct_key = printer.get_active_spool_key()
        if deduct_key is None and not has_ams_hardware:
            deduct_key = AMSSlot.EXTERNAL.value

    if deduct_key is not None:
        printer._current_job_slot_key = deduct_key
        printer.last_active_slot = deduct_key

    # Deduct weight from selected slot or active slot
    w_g = getattr(printer, "_current_job_grams", 0.0)
    printer._job_started_from_app = True
    if w_g > 0 and not getattr(printer, "_job_deducted", False) and deduct_key is not None:
        old_w = printer.get_slot_grams(deduct_key)
        new_w = max(0.0, round(old_w - w_g, 2))
        printer.set_slot_grams(new_w, deduct_key)
        printer._job_deducted = True
        printer.last_job_grams = w_g
        printer._deduct_spool_warehouse(deduct_key, w_g)
        logger.info(
            f"💾 Auto-deducted {w_g}g from Slot {deduct_key} for [{printer.name}]. Old: {old_w}g -> New: {new_w}g"
        )
        printer._trigger_save()

    timestamp_id = str(int(time.time()))

    if ams_mapping is not None:
        ams_mapping_list = ams_mapping
        use_ams_bool = bool(ams_mapping_list) and use_ams and has_ams_hardware
    else:
        ams_mapping_list, use_ams_bool = build_ams_mapping_fn(target_slot, has_ams_hardware, use_ams)

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
        printer._client.publish(f"device/{printer.serial_number}/request", json.dumps(payload))
        logger.info(
            f"🚀 Sent MQTT project_file command for {clean_file} (url: {url_path}, md5: {md5_str}) to [{printer.name}]"
        )
        return (
            True,
            f"✅ Файл <code>{html.escape(filename)}</code> успішно відправлено по FTPS та запущено на друк на <b>{html.escape(printer.name)}</b>!",
        )
    except Exception as e:
        logger.error(f"Error publishing MQTT project_file for [{printer.name}]: {e}")
        return False, f"⚠️ Помилка відправки MQTT команди на друк: {e}"
