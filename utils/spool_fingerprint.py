"""
spool_fingerprint.py - Builds a unique fingerprint hash of the printer's AMS + external spool configuration,
and handles persistent active print context storage across bot restarts.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional
from config import STORAGE_DIR, logger

CONTEXT_FILE = STORAGE_DIR / "active_print_contexts.json"
DB_PATH = STORAGE_DIR / "printer_farm.db"


def build_spool_fingerprint(printer: Any) -> str:
    """
    Builds a unique fingerprint of current AMS slots, filament types, colors, and remaining weights.
    Format: '0=PLA|#FF0000|1000.0;1=PETG|#00FF00|850.0;...'
    """
    parts = []
    ams_slots = getattr(printer, "ams_slots", {}) or {}
    ams_trays = getattr(printer, "ams_trays_info", {}) or {}

    for slot_key in sorted(ams_slots.keys()):
        weight = ams_slots[slot_key]
        tray_info = ams_trays.get(slot_key, {}) if isinstance(ams_trays, dict) else {}
        ftype = str(tray_info.get("type") or getattr(printer, "filament_type", "") or "")
        color = str(tray_info.get("color") or getattr(printer, "tray_color", "") or "")
        parts.append(f"{slot_key}={ftype}|{color}|{weight}")

    return ";".join(parts)


def save_active_print_context(printer_id: str, context_data: dict[str, Any]) -> None:
    """
    Saves active print context to SQLite DB kv_store and active_print_contexts.json cache.
    """
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        key = f"active_context_{printer_id}"
        val_str = json.dumps(context_data, ensure_ascii=False)

        # Save to SQLite DB kv_store table if available
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES (?, ?, ?)",
                    (key, val_str, time.time()),
                )
                conn.commit()
            finally:
                conn.close()

        # Also persist into active_print_contexts.json
        data = {}
        if CONTEXT_FILE.exists():
            try:
                data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[printer_id] = context_data
        CONTEXT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"💾 Saved active print context for printer [{printer_id}] to disk.")
    except Exception as e:
        logger.warning(f"Failed saving active print context for [{printer_id}]: {e}")


def load_active_print_context(printer_id: str) -> Optional[dict[str, Any]]:
    """
    Loads saved active print context for a printer from SQLite DB or JSON cache.
    """
    key = f"active_context_{printer_id}"
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                cur = conn.execute("SELECT val FROM kv_store WHERE key = ?", (key,))
                row = cur.fetchone()
                if row:
                    return json.loads(row[0])
            finally:
                conn.close()
        except Exception:
            pass

    if CONTEXT_FILE.exists():
        try:
            data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and printer_id in data:
                return data[printer_id]
        except Exception:
            pass
    return None


def delete_active_print_context(printer_id: str) -> None:
    """
    Deletes active print context when print job finishes or fails.
    """
    try:
        key = f"active_context_{printer_id}"
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                conn.execute("DELETE FROM kv_store WHERE key = ?", (key,))
                conn.commit()
            finally:
                conn.close()

        if CONTEXT_FILE.exists():
            try:
                data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and printer_id in data:
                    del data[printer_id]
                    CONTEXT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        logger.info(f"🗑️ Deleted active print context for printer [{printer_id}].")
    except Exception as e:
        logger.warning(f"Failed deleting active print context for [{printer_id}]: {e}")
