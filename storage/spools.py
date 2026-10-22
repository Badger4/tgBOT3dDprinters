"""
Repository for filament spools and warehouse audit movements.
Backed by relational SQLite tables with atomic deductions and disk snapshot sync.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class SpoolRepository(BaseStorage):
    """Handles async persistence for filament spools and weight audit logs."""

    async def load_spools(self) -> dict[str, dict[str, Any]]:
        """Loads all active spools from SQLite storage."""
        default_spools = {
            "spool_1": {
                "id": "spool_1",
                "name": "Sunlu PLA Black",
                "brand": "Sunlu",
                "type": "PLA",
                "color": "Black",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 650.0,
            },
            "spool_2": {
                "id": "spool_2",
                "name": "eSUN PETG Grey",
                "brand": "eSUN",
                "type": "PETG",
                "color": "Grey",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 700.0,
            },
        }

        def _query_db() -> dict[str, dict[str, Any]]:
            conn = self._get_db()
            try:
                cur = conn.execute("SELECT id, data_json FROM spools WHERE is_active = 1")
                rows = cur.fetchall()
                if rows:
                    res = {}
                    for row in rows:
                        try:
                            s = json.loads(row[1])
                            rem_g = float(s.get("remaining_grams", 1000.0))
                            if rem_g > 0.0:
                                res[row[0]] = s
                        except Exception:
                            pass
                    return res
                return {}
            finally:
                conn.close()

        db_spools = await asyncio.to_thread(_query_db)
        if db_spools:
            return db_spools

        # Fallback to kv_store or legacy JSON file
        legacy_data = await self.load_json(self.spools_file, default_spools)
        raw_dict = {}
        if isinstance(legacy_data, list):
            raw_dict = {s["id"]: s for s in legacy_data if isinstance(s, dict) and "id" in s}
        elif isinstance(legacy_data, dict):
            raw_dict = legacy_data
        else:
            raw_dict = default_spools

        filtered = {}
        for s_id, s in raw_dict.items():
            if isinstance(s, dict):
                try:
                    rem_g = float(s.get("remaining_grams", 1000.0))
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    filtered[s_id] = s

        if filtered:
            await self.save_spools(filtered)
        return filtered

    async def save_spools(self, spools: dict[str, dict[str, Any]] | list[dict[str, Any]]) -> bool:
        """Saves filament spools to SQLite and syncs atomic disk snapshot."""
        now = time.time()
        if isinstance(spools, list):
            spool_dict = {str(s.get("id") or s.get("spool_id") or i): s for i, s in enumerate(spools) if isinstance(s, dict)}
        elif isinstance(spools, dict):
            spool_dict = spools
        else:
            spool_dict = {}

        filtered = {}
        for s_id, s in spool_dict.items():
            if isinstance(s, dict):
                try:
                    rem_val = s.get("remaining_grams") if s.get("remaining_grams") is not None else s.get("remaining_weight")
                    rem_g = float(rem_val if rem_val is not None else 1000.0)
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    s["remaining_grams"] = rem_g
                    filtered[s_id] = s

        val_str = json.dumps(filtered, ensure_ascii=False)

        def _write_db() -> bool:
            conn = self._get_db()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                current_ids = set(filtered.keys())
                if current_ids:
                    placeholders = ",".join("?" for _ in current_ids)
                    conn.execute(f"DELETE FROM spools WHERE id NOT IN ({placeholders})", list(current_ids))
                else:
                    conn.execute("DELETE FROM spools")

                for s_id, s in filtered.items():
                    name = str(s.get("name") or s_id)
                    brand = str(s.get("brand") or "")
                    s_type = str(s.get("type") or s.get("material") or "PLA")
                    color = str(s.get("color") or s.get("color_hex") or "")
                    rem_val = s.get("remaining_grams") if s.get("remaining_grams") is not None else s.get("remaining_weight")
                    rem_g = float(rem_val if rem_val is not None else 1000.0)
                    total_g = float(s.get("total_grams") or s.get("spool_weight") or 1000.0)
                    price = float(s.get("price_uah") or s.get("price_per_kg") or 650.0)
                    assigned_p = s.get("assigned_printer_id")
                    assigned_p_str = str(assigned_p) if assigned_p else None
                    assigned_slot = s.get("assigned_slot_key") if s.get("assigned_slot_key") is not None else s.get("assigned_slot")
                    assigned_slot_str = str(assigned_slot) if assigned_slot is not None else None
                    if assigned_slot_str is not None:
                        s["assigned_slot_key"] = assigned_slot_str
                    if assigned_p_str is not None:
                        s["assigned_printer_id"] = assigned_p_str
                    s_json = json.dumps(s, ensure_ascii=False)

                    conn.execute(
                        """
                        INSERT INTO spools (id, name, brand, type, color, remaining_grams, total_grams, price_uah, assigned_printer_id, assigned_slot_key, is_active, data_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name=excluded.name,
                            brand=excluded.brand,
                            type=excluded.type,
                            color=excluded.color,
                            remaining_grams=excluded.remaining_grams,
                            total_grams=excluded.total_grams,
                            price_uah=excluded.price_uah,
                            assigned_printer_id=excluded.assigned_printer_id,
                            assigned_slot_key=excluded.assigned_slot_key,
                            is_active=1,
                            data_json=excluded.data_json,
                            updated_at=excluded.updated_at
                        """,
                        (s_id, name, brand, s_type, color, rem_g, total_g, price, assigned_p_str, assigned_slot_str, s_json, now),
                    )

                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('spools.json', ?, ?)",
                    (val_str, now),
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"SQLite save_spools error: {e}")
                return False
            finally:
                conn.close()

        ok = await asyncio.to_thread(_write_db)
        if ok:
            await asyncio.to_thread(self._atomic_write_file, self.spools_file, val_str)
        return ok

    async def load_spool_movements(self, spool_id: str | None = None) -> list[dict[str, Any]]:
        """Loads warehouse movement audit history from SQLite, optionally filtered by spool_id."""
        def _query_db() -> list[dict[str, Any]]:
            conn = self._get_db()
            try:
                if spool_id:
                    cur = conn.execute(
                        """
                        SELECT id, timestamp, spool_id, spool_name, movement_type, weight_delta, final_weight, reason, printer_id, user_id
                        FROM warehouse_movements
                        WHERE spool_id = ?
                        ORDER BY timestamp ASC
                        LIMIT 2000
                        """,
                        (spool_id,),
                    )
                else:
                    cur = conn.execute(
                        """
                        SELECT id, timestamp, spool_id, spool_name, movement_type, weight_delta, final_weight, reason, printer_id, user_id
                        FROM warehouse_movements
                        ORDER BY timestamp ASC
                        LIMIT 2000
                        """
                    )
                rows = cur.fetchall()
                if rows:
                    res = []
                    for r in rows:
                        res.append({
                            "id": f"mov_{r[0]}",
                            "timestamp": r[1],
                            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r[1])),
                            "spool_id": r[2],
                            "spool_name": r[3] or "Котушка",
                            "action": r[4],
                            "movement_type": r[4],
                            "weight_change_g": round(float(r[5]), 2),
                            "weight_delta": round(float(r[5]), 2),
                            "prev_weight_g": round(float(r[6] - r[5]), 2),
                            "new_weight_g": round(float(r[6]), 2),
                            "final_weight": round(float(r[6]), 2),
                            "reason": r[7] or r[4],
                            "printer_id": r[8],
                            "user": r[9] or r[8] or "System",
                        })
                    return res
                return []
            finally:
                conn.close()

        movements = await asyncio.to_thread(_query_db)
        if movements:
            return movements

        raw_movements = await self.load_json(self.movements_file, [])
        if spool_id:
            return [m for m in raw_movements if m.get("spool_id") == spool_id]
        return raw_movements

    async def record_spool_movement(
        self,
        spool_id: str,
        spool_name: str,
        action: str,
        weight_change_g: float,
        prev_weight_g: float,
        new_weight_g: float,
        reason: str = "",
        user: str = "System",
    ) -> dict[str, Any]:
        """Records a spool weight movement / audit log entry in SQLite and syncs disk replica."""
        now = time.time()
        entry = {
            "id": f"mov_{int(now * 1000)}",
            "timestamp": now,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "spool_id": spool_id,
            "spool_name": spool_name,
            "action": action,
            "weight_change_g": round(float(weight_change_g), 2),
            "prev_weight_g": round(float(prev_weight_g), 2),
            "new_weight_g": round(float(new_weight_g), 2),
            "reason": reason or action,
            "user": user,
        }

        def _insert_db() -> bool:
            conn = self._get_db()
            try:
                conn.execute(
                    """
                    INSERT INTO warehouse_movements (timestamp, spool_id, spool_name, movement_type, weight_delta, final_weight, reason, user_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (now, spool_id, spool_name, action, weight_change_g, new_weight_g, reason, user, now),
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error recording movement in SQLite: {e}")
                return False
            finally:
                conn.close()

        await asyncio.to_thread(_insert_db)

        # Mirror in movements_file for legacy consumers
        async with self.transaction_lock("movements"):
            movements = await self.load_json(self.movements_file, [])
            movements.append(entry)
            if len(movements) > 1000:
                movements = movements[-1000:]
            await self.save_json(self.movements_file, movements)

        logger.info(
            f"📦 [Warehouse Audit] Spool [{spool_name}] ({spool_id}) action='{action}' "
            f"change={weight_change_g:+.1f}g ({prev_weight_g:.1f}g -> {new_weight_g:.1f}g) by {user}. Reason: {reason}"
        )
        return entry

    async def deduct_spool_warehouse_atomic(
        self,
        printer_id: str,
        printer_name: str,
        slot_key: str,
        deducted_grams: float,
        subtask_name: str | None = None,
    ) -> bool:
        """
        Atomically deducts grams from the mounted spool and logs the audit movement
        inside a single ACID SQLite transaction, preventing race conditions or desync on crash.
        """
        if deducted_grams <= 0:
            return False

        async with self.transaction_lock("spools"):
            def _tx_deduct() -> tuple[bool, str, str, float, float, dict[str, Any]]:
                conn = self._get_db()
                try:
                    conn.execute("BEGIN IMMEDIATE;")
                    target_slot_str = str(slot_key)
                    allowed_slots = ["254", "255"] if target_slot_str in ["254", "255"] else [target_slot_str]
                    placeholders = ",".join("?" for _ in allowed_slots)

                    cur = conn.execute(
                        f"""
                        SELECT id, name, remaining_grams, data_json 
                        FROM spools 
                        WHERE assigned_printer_id = ? AND assigned_slot_key IN ({placeholders})
                        LIMIT 1
                        """,
                        [printer_id] + allowed_slots,
                    )
                    row = cur.fetchone()
                    if not row:
                        conn.rollback()
                        return False, "", "", 0.0, 0.0, {}

                    s_id, s_name, prev_w, data_str = row
                    try:
                        s_data = json.loads(data_str)
                    except Exception:
                        s_data = {}

                    new_w = max(0.0, round(float(prev_w) - deducted_grams, 2))
                    s_data["remaining_grams"] = new_w
                    now = time.time()
                    new_json = json.dumps(s_data, ensure_ascii=False)

                    # Update spool
                    conn.execute(
                        "UPDATE spools SET remaining_grams = ?, data_json = ?, updated_at = ? WHERE id = ?",
                        (new_w, new_json, now, s_id),
                    )

                    # Record movement
                    reason = f"Друк: {subtask_name or 'Завдання'}"
                    conn.execute(
                        """
                        INSERT INTO warehouse_movements 
                        (timestamp, spool_id, spool_name, movement_type, weight_delta, final_weight, reason, printer_id, user_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (now, s_id, s_name, "print", -round(deducted_grams, 2), new_w, reason, printer_id, printer_name, now),
                    )

                    # Update kv_store snapshot
                    cur_all = conn.execute("SELECT id, data_json FROM spools WHERE is_active = 1")
                    all_spools = {r[0]: json.loads(r[1]) for r in cur_all.fetchall()}
                    conn.execute(
                        "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('spools.json', ?, ?)",
                        (json.dumps(all_spools, ensure_ascii=False), now),
                    )

                    conn.commit()
                    return True, s_id, s_name, prev_w, new_w, all_spools
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error in deduct_spool_warehouse_atomic for [{printer_name}]: {e}")
                    return False, "", "", 0.0, 0.0, {}
                finally:
                    conn.close()

            ok, s_id, s_name, prev_w, new_w, all_spools = await asyncio.to_thread(_tx_deduct)
            if ok:
                await asyncio.to_thread(self._atomic_write_file, self.spools_file, json.dumps(all_spools, ensure_ascii=False))
                logger.info(
                    f"📦 [Warehouse Audit Atomic] Spool [{s_name}] ({s_id}) deducted {deducted_grams:.1f}g "
                    f"({prev_w:.1f}g -> {new_w:.1f}g) on [{printer_name}]."
                )
            return ok
