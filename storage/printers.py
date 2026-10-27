"""
Repository for 3D printer fleet persistence with relational SQLite backing,
atomic cascading deletions, and transactional integrity.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class PrinterRepository(BaseStorage):
    """Handles async persistence for 3D printer credentials, telemetry, and fleet operations."""

    async def load_printers(self) -> dict[str, Any]:
        """Loads all registered 3D printers from SQLite storage."""
        def _query_db() -> dict[str, Any]:
            conn = self._get_db()
            try:
                cur = conn.execute("SELECT id, config_json FROM printers")
                rows = cur.fetchall()
                if rows:
                    res = {}
                    for row in rows:
                        try:
                            p_dict = json.loads(row[1])
                            res[row[0]] = p_dict
                        except Exception:
                            pass
                    return res
                return {}
            finally:
                conn.close()

        printers_dict = await asyncio.to_thread(_query_db)
        if printers_dict:
            return printers_dict

        # Fallback to kv_store or printers.json on disk and migrate into relational table
        legacy_data = await self.load_json(self.printers_file, {}, bypass_redirect=True)
        loaded = {}
        if isinstance(legacy_data, list):
            loaded = {p["id"]: p for p in legacy_data if isinstance(p, dict) and "id" in p}
        elif isinstance(legacy_data, dict):
            loaded = legacy_data

        if loaded:
            await self.save_printers(loaded)
        return loaded

    async def save_printers(self, printers: dict[str, Any] | list[dict[str, Any]]) -> bool:
        """Saves registered 3D printers configuration to SQLite printers table and disk replica."""
        if isinstance(printers, dict):
            printers_list = list(printers.values())
        elif isinstance(printers, list):
            printers_list = printers
        else:
            printers_list = []

        now = time.time()
        val_str = json.dumps(printers, ensure_ascii=False)

        def _write_db() -> bool:
            conn = self._get_db()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                # Sync relational table: remove printers no longer present
                current_ids = {str(p.get("id")) for p in printers_list if isinstance(p, dict) and p.get("id")}
                if current_ids:
                    placeholders = ",".join("?" for _ in current_ids)
                    conn.execute(f"DELETE FROM printers WHERE id NOT IN ({placeholders})", list(current_ids))
                else:
                    conn.execute("DELETE FROM printers")

                for p in printers_list:
                    if not isinstance(p, dict) or not p.get("id"):
                        continue
                    p_id = str(p["id"])
                    name = str(p.get("name") or p_id)
                    model = str(p.get("printer_model") or p.get("model") or "")
                    ip = str(p.get("ip") or "")
                    code = str(p.get("access_code") or p.get("accessCode") or "")
                    serial = str(p.get("serial") or p.get("serialNumber") or p.get("serial_number") or "")
                    has_ams = 1 if p.get("has_ams") else 0
                    config_json = json.dumps(p, ensure_ascii=False)

                    conn.execute(
                        """
                        INSERT INTO printers (id, name, model, ip, access_code, serial, has_ams, config_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name=excluded.name,
                            model=excluded.model,
                            ip=excluded.ip,
                            access_code=excluded.access_code,
                            serial=excluded.serial,
                            has_ams=excluded.has_ams,
                            config_json=excluded.config_json,
                            updated_at=excluded.updated_at
                        """,
                        (p_id, name, model, ip, code, serial, has_ams, config_json, now),
                    )

                # Mirror into kv_store for backward-compatibility
                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('printers.json', ?, ?)",
                    (val_str, now),
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"SQLite save_printers error: {e}")
                return False
            finally:
                conn.close()

        lock = self._get_lock(self.printers_file)
        async with lock:
            ok = await asyncio.to_thread(_write_db)
            if ok:
                # Atomically flush disk replica
                await asyncio.to_thread(self._atomic_write_file, self.printers_file, val_str)
            return ok

    async def delete_printer_atomic(self, printer_id: str) -> bool:
        """
        Atomically deletes a printer and cleans up all dependent entities in a single ACID transaction:
        1. Unmounts all spools attached to this printer (clearing assigned_printer_id and assigned_slot_key).
        2. Logs warehouse movement audit records for unmounted spools.
        3. Deletes active print context for this printer.
        4. Deletes printer from SQLite and updates disk replica.
        Guarantees zero ghost printers or orphaned spools even on crash/power cut.
        """
        async with self.transaction_lock("fleet_mutation"):
            def _tx_delete() -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
                conn = self._get_db()
                try:
                    conn.execute("BEGIN IMMEDIATE;")
                    now = time.time()

                    cur_chk = conn.execute("SELECT id FROM printers WHERE id = ?", (printer_id,))
                    if not cur_chk.fetchone():
                        conn.rollback()
                        return False, [], {}

                    # 1. Unmount spools assigned to this printer
                    cur = conn.execute(
                        "SELECT id, name, remaining_grams, data_json FROM spools WHERE assigned_printer_id = ?",
                        (printer_id,),
                    )
                    unmounted_spools = []
                    for row in cur.fetchall():
                        s_id, s_name, rem_g, data_str = row
                        try:
                            s_data = json.loads(data_str)
                        except Exception:
                            s_data = {}
                        s_data["assigned_printer_id"] = None
                        s_data["assigned_slot_key"] = None
                        unmounted_spools.append((s_id, s_name, rem_g, json.dumps(s_data, ensure_ascii=False)))

                    for s_id, s_name, rem_g, new_json in unmounted_spools:
                        conn.execute(
                            "UPDATE spools SET assigned_printer_id = NULL, assigned_slot_key = NULL, data_json = ?, updated_at = ? WHERE id = ?",
                            (new_json, now, s_id),
                        )
                        conn.execute(
                            """
                            INSERT INTO warehouse_movements 
                            (timestamp, spool_id, spool_name, movement_type, weight_delta, final_weight, reason, printer_id, user_id, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (now, s_id, s_name, "unassign", 0.0, rem_g, "Знято через видалення принтера", printer_id, "System", now),
                        )

                    # 2. Delete print context
                    conn.execute("DELETE FROM print_contexts WHERE printer_id = ?", (printer_id,))
                    conn.execute("DELETE FROM kv_store WHERE key = ?", (f"active_context_{printer_id}",))

                    # 3. Delete printer record
                    conn.execute("DELETE FROM printers WHERE id = ?", (printer_id,))

                    # 4. Fetch remaining printers and spools for disk sync
                    cur_p = conn.execute("SELECT config_json FROM printers")
                    remaining_printers = [json.loads(r[0]) for r in cur_p.fetchall()]

                    cur_s = conn.execute("SELECT id, data_json FROM spools WHERE is_active = 1")
                    remaining_spools = {r[0]: json.loads(r[1]) for r in cur_s.fetchall()}

                    # Update kv_store copies as well
                    conn.execute(
                        "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES (?, ?, ?)",
                        ("printers.json", json.dumps(remaining_printers, ensure_ascii=False), now),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES (?, ?, ?)",
                        ("spools.json", json.dumps(remaining_spools, ensure_ascii=False), now),
                    )

                    conn.commit()
                    return True, remaining_printers, remaining_spools
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error in delete_printer_atomic for {printer_id}: {e}")
                    return False, [], {}
                finally:
                    conn.close()

            ok, remaining_printers, remaining_spools = await asyncio.to_thread(_tx_delete)
            if ok:
                await asyncio.to_thread(self._atomic_write_file, self.printers_file, json.dumps(remaining_printers, ensure_ascii=False))
                await asyncio.to_thread(self._atomic_write_file, self.spools_file, json.dumps(remaining_spools, ensure_ascii=False))
                try:
                    from utils.spool_fingerprint import delete_active_print_context
                    delete_active_print_context(printer_id)
                except Exception:
                    pass
            return ok
