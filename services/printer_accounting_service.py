"""
Service for printer warehouse accounting and history logging.
Decoupled from models/printer.py to adhere to the Single Responsibility Principle (SRP).
"""
import asyncio
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)


def deduct_spool_warehouse(
    storage: Any,
    printer_id: str,
    printer_name: str,
    slot_key: str,
    deducted_grams: float,
    subtask_name: str | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Deducts grams from the spool mounted to the specified printer and slot in warehouse storage,
    and logs an audit movement record. Thread-safe from sync or async contexts.
    """
    if not storage or deducted_grams <= 0:
        return

    async def _do_deduct() -> None:
        try:
            async with storage.transaction_lock("spools"):
                spools = await storage.load_spools()
                spool_to_deduct = None
                spool_id_to_deduct = None
                target_slot_str = str(slot_key)
                allowed_slots = ["254", "255"] if target_slot_str in ["254", "255"] else [target_slot_str]
                for s_id, s in spools.items():
                    if s.get("assigned_printer_id") == printer_id and str(s.get("assigned_slot_key")) in allowed_slots:
                        spool_to_deduct = s
                        spool_id_to_deduct = s_id
                        break

                if spool_to_deduct and spool_id_to_deduct:
                    prev_w = float(spool_to_deduct.get("remaining_grams", 0.0))
                    new_w = max(0.0, round(prev_w - deducted_grams, 2))
                    spool_to_deduct["remaining_grams"] = new_w
                    spools[spool_id_to_deduct] = spool_to_deduct
                    await storage.save_spools(spools)
                    await storage.record_spool_movement(
                        spool_id=spool_id_to_deduct,
                        spool_name=spool_to_deduct.get("name", "Котушка"),
                        action="print",
                        weight_change_g=-round(deducted_grams, 2),
                        prev_weight_g=round(prev_w, 2),
                        new_weight_g=new_w,
                        reason=f"Друк: {subtask_name or 'Завдання'}",
                        user=printer_name,
                    )
        except Exception as ex:
            logger.warning(f"Error in deduct_spool_warehouse async task for [{printer_name}]: {ex}")

    try:
        current_loop = None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        target_loop = current_loop or loop
        if current_loop and current_loop.is_running():
            current_loop.create_task(_do_deduct())
            return

        if target_loop and target_loop.is_running():
            asyncio.run_coroutine_threadsafe(_do_deduct(), target_loop)
        else:
            logger.warning(f"No running loop available for deduct_spool_warehouse [{printer_name}]")
    except Exception as e:
        logger.warning(f"Failed to schedule deduct_spool_warehouse for [{printer_name}]: {e}")


def record_print_history_entry(
    storage: Any,
    printer: Any,
    final_weight: float,
    note_text: str = "",
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Constructs and persists a completed print job history entry in storage.
    Thread-safe from MQTT thread or async loop.
    """
    if not storage:
        return

    raw_title = str(
        getattr(printer, "_custom_job_name", None)
        or getattr(printer, "subtask_name", None)
        or "Деталь 3D"
    ).strip()

    if raw_title.endswith(".gcode.3mf"):
        raw_title = raw_title.rsplit(".", 2)[0]
    elif raw_title.endswith((".3mf", ".gcode")):
        raw_title = raw_title.rsplit(".", 1)[0]

    clean_subtask = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_title).strip()
    if not clean_subtask or clean_subtask.lower() in ["untitled", "none", "null"] or re.match(r"^[_ -]+$", clean_subtask):
        clean_subtask = "Деталь 3D"

    entry = {
        "timestamp": time.time(),
        "printer_name": printer.name,
        "printer_id": printer.id,
        "printer_sn": getattr(printer, "serial_number", getattr(printer, "sn", printer.id)),
        "subtask_name": clean_subtask,
        "weight_g": round(float(final_weight), 1),
        "filament_type": getattr(printer, "filament_type", ""),
        "note": note_text,
    }

    try:
        current_loop = None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        target_loop = current_loop or loop
        if current_loop and current_loop.is_running():
            current_loop.create_task(storage.add_history_entry(entry))
            return

        if target_loop and target_loop.is_running():
            asyncio.run_coroutine_threadsafe(storage.add_history_entry(entry), target_loop)
        else:
            logger.warning(f"⚠️ Event loop unresolvable for history entry on [{printer.name}]")
    except Exception as e:
        logger.warning(f"Failed to record history entry for [{printer.name}]: {e}")
