"""
Repository for 3D printed parts catalog and 3MF files.
Backed by SQLite relational table and atomic disk snapshots.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class PartRepository(BaseStorage):
    """Handles async persistence for finished printed parts inventory."""

    async def load_parts(self) -> dict[str, dict[str, Any]]:
        def _query_db() -> dict[str, dict[str, Any]]:
            conn = self._get_db()
            try:
                cur = conn.execute("SELECT id, data_json FROM parts")
                rows = cur.fetchall()
                if rows:
                    res = {}
                    for row in rows:
                        try:
                            res[row[0]] = json.loads(row[1])
                        except Exception:
                            pass
                    return res
                return {}
            finally:
                conn.close()

        db_parts = await asyncio.to_thread(_query_db)
        if db_parts:
            return db_parts

        data = await self.load_json(self.parts_file, {})
        res = {}
        if isinstance(data, list):
            res = {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
        elif isinstance(data, dict):
            res = data

        if res:
            await self.save_parts(res)
        return res

    async def save_parts(self, parts: dict[str, dict[str, Any]] | list[dict[str, Any]]) -> bool:
        now = time.time()
        if isinstance(parts, list):
            parts_dict = {str(p.get("id") or i): p for i, p in enumerate(parts) if isinstance(p, dict)}
        elif isinstance(parts, dict):
            parts_dict = parts
        else:
            parts_dict = {}

        val_str = json.dumps(parts_dict, ensure_ascii=False)

        def _write_db() -> bool:
            conn = self._get_db()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                current_ids = set(parts_dict.keys())
                if current_ids:
                    placeholders = ",".join("?" for _ in current_ids)
                    conn.execute(f"DELETE FROM parts WHERE id NOT IN ({placeholders})", list(current_ids))
                else:
                    conn.execute("DELETE FROM parts")

                for p_id, p_data in parts_dict.items():
                    name = str(p_data.get("name") or p_id)
                    count = int(p_data.get("count", 0))
                    qty = int(p_data.get("quantity", count))
                    image = str(p_data.get("image") or "")
                    three_mf = str(p_data.get("three_mf") or "")
                    p_json = json.dumps(p_data, ensure_ascii=False)

                    conn.execute(
                        """
                        INSERT INTO parts (id, name, count, quantity, image, three_mf, data_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name=excluded.name,
                            count=excluded.count,
                            quantity=excluded.quantity,
                            image=excluded.image,
                            three_mf=excluded.three_mf,
                            data_json=excluded.data_json,
                            updated_at=excluded.updated_at
                        """,
                        (p_id, name, count, qty, image, three_mf, p_json, now),
                    )

                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('parts.json', ?, ?)",
                    (val_str, now),
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Error saving parts to SQLite: {e}")
                return False
            finally:
                conn.close()

        ok = await asyncio.to_thread(_write_db)
        if ok:
            await asyncio.to_thread(self._atomic_write_file, self.parts_file, val_str)
        return ok
