"""
spool_fingerprint.py - Builds a unique fingerprint hash of the printer's AMS + external spool configuration,
and handles persistent active print context storage backed by SQLite and crash-proof atomic snapshots.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from config import STORAGE_DIR, logger

CONTEXT_FILE = STORAGE_DIR / "active_print_contexts.json"
DB_PATH = STORAGE_DIR / "printer_farm.db"


_CONTEXT_MEMORY_CACHE: dict[str, dict[str, Any]] = {}
_CONTEXT_CACHE_LOADED: bool = False


def _atomic_write_context_file(content: str) -> None:
    """Atomically writes context file via temp file + replace to prevent corruption."""
    try:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = CONTEXT_FILE.with_suffix(f"{CONTEXT_FILE.suffix}.tmp.{os.getpid()}.{time.time()}")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, CONTEXT_FILE)
    except Exception as e:
        logger.warning(f"Failed to sync atomic context file replica: {e}")


def _ensure_cache_loaded() -> None:
    global _CONTEXT_CACHE_LOADED
    if _CONTEXT_CACHE_LOADED:
        return
    _CONTEXT_CACHE_LOADED = True

    # 1. Load from SQLite print_contexts table
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                cur = conn.execute("SELECT printer_id, context_json FROM print_contexts")
                rows = cur.fetchall()
                if rows:
                    for row in rows:
                        p_id, c_json = row[0], row[1]
                        try:
                            _CONTEXT_MEMORY_CACHE[p_id] = json.loads(c_json)
                        except Exception:
                            pass
                else:
                    # Fallback to kv_store
                    cur2 = conn.execute("SELECT key, val FROM kv_store WHERE key LIKE 'active_context_%'")
                    for row2 in cur2.fetchall():
                        k, v = row2[0], row2[1]
                        p_id = k.replace("active_context_", "")
                        try:
                            _CONTEXT_MEMORY_CACHE[p_id] = json.loads(v)
                        except Exception:
                            pass
            finally:
                conn.close()
        except Exception:
            pass

    # 2. Fallback/merge from JSON file if DB had nothing
    if not _CONTEXT_MEMORY_CACHE and CONTEXT_FILE.exists():
        try:
            data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for p_id, val in data.items():
                    if p_id not in _CONTEXT_MEMORY_CACHE and isinstance(val, dict):
                        _CONTEXT_MEMORY_CACHE[p_id] = val
        except Exception:
            pass


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
    Saves active print context to SQLite DB print_contexts table and crash-proof atomic JSON cache.
    """
    try:
        _ensure_cache_loaded()
        _CONTEXT_MEMORY_CACHE[printer_id] = context_data

        now = time.time()
        subtask = str(context_data.get("subtask_name") or "")
        fp = str(context_data.get("spool_fingerprint") or "")
        layer = int(context_data.get("saved_layer", 0))
        prog = int(context_data.get("progress_pct", 0))
        grams = float(context_data.get("job_grams", 0.0))
        deducted = 1 if context_data.get("job_deducted") else 0
        val_str = json.dumps(context_data, ensure_ascii=False)

        # Save to SQLite DB print_contexts and kv_store tables
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                conn.execute(
                    """
                    INSERT INTO print_contexts (printer_id, subtask_name, spool_fingerprint, saved_layer, progress_pct, job_grams, job_deducted, context_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(printer_id) DO UPDATE SET
                        subtask_name=excluded.subtask_name,
                        spool_fingerprint=excluded.spool_fingerprint,
                        saved_layer=excluded.saved_layer,
                        progress_pct=excluded.progress_pct,
                        job_grams=excluded.job_grams,
                        job_deducted=excluded.job_deducted,
                        context_json=excluded.context_json,
                        updated_at=excluded.updated_at
                    """,
                    (printer_id, subtask, fp, layer, prog, grams, deducted, val_str, now),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES (?, ?, ?)",
                    (f"active_context_{printer_id}", val_str, now),
                )
                conn.commit()
            finally:
                conn.close()

        # Atomically flush to active_print_contexts.json
        _atomic_write_context_file(json.dumps(_CONTEXT_MEMORY_CACHE, indent=2, ensure_ascii=False))
        logger.info(f"💾 Saved active print context for printer [{printer_id}] to DB & atomic snapshot.")
    except Exception as e:
        logger.warning(f"Failed saving active print context for [{printer_id}]: {e}")


record_active_print_context = save_active_print_context


def load_active_print_context(printer_id: str) -> Optional[dict[str, Any]]:
    """
    Loads saved active print context for a printer from in-memory cache or SQLite DB.
    """
    _ensure_cache_loaded()
    if printer_id in _CONTEXT_MEMORY_CACHE:
        return _CONTEXT_MEMORY_CACHE[printer_id]

    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                cur = conn.execute("SELECT context_json FROM print_contexts WHERE printer_id = ?", (printer_id,))
                row = cur.fetchone()
                if row and row[0]:
                    val = json.loads(row[0])
                    _CONTEXT_MEMORY_CACHE[printer_id] = val
                    return val
                # Fallback to kv_store
                cur2 = conn.execute("SELECT val FROM kv_store WHERE key = ?", (f"active_context_{printer_id}",))
                row2 = cur2.fetchone()
                if row2 and row2[0]:
                    val = json.loads(row2[0])
                    _CONTEXT_MEMORY_CACHE[printer_id] = val
                    return val
            finally:
                conn.close()
        except Exception:
            pass

    if CONTEXT_FILE.exists():
        try:
            data = json.loads(CONTEXT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and printer_id in data:
                val = data[printer_id]
                _CONTEXT_MEMORY_CACHE[printer_id] = val
                return val
        except Exception:
            pass
    return None


def delete_active_print_context(printer_id: str) -> None:
    """
    Deletes active print context when print job finishes, fails, or printer is deleted.
    """
    _ensure_cache_loaded()

    if printer_id in _CONTEXT_MEMORY_CACHE:
        _CONTEXT_MEMORY_CACHE.pop(printer_id, None)

    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(DB_PATH, timeout=5.0)
            try:
                conn.execute("DELETE FROM print_contexts WHERE printer_id = ?", (printer_id,))
                conn.execute("DELETE FROM kv_store WHERE key = ?", (f"active_context_{printer_id}",))
                conn.commit()
            finally:
                conn.close()

        _atomic_write_context_file(json.dumps(_CONTEXT_MEMORY_CACHE, indent=2, ensure_ascii=False))
        logger.info(f"🗑️ Deleted active print context for printer [{printer_id}].")
    except Exception as e:
        logger.warning(f"Failed deleting active print context for [{printer_id}]: {e}")
