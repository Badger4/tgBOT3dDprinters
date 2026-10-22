"""
Repository for global 3D printer farm settings.
Backed by SQLite relational table and atomic disk snapshots.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class SettingsRepository(BaseStorage):
    """Handles async persistence for farm-wide settings."""

    async def load_settings(self) -> dict[str, Any]:
        """Loads global settings from SQLite storage."""
        def _query_db() -> dict[str, Any]:
            conn = self._get_db()
            try:
                cur = conn.execute("SELECT val FROM settings WHERE key = 'global'")
                row = cur.fetchone()
                if row and row[0]:
                    try:
                        return json.loads(row[0])
                    except Exception:
                        pass
                return {}
            finally:
                conn.close()

        db_settings = await asyncio.to_thread(_query_db)
        if db_settings:
            return db_settings

        data = await self.load_json(self.settings_file, {})
        res = data if isinstance(data, dict) else {}
        if res:
            await self.save_settings(res)
        return res

    async def save_settings(self, settings: dict[str, Any]) -> bool:
        """Saves global settings to SQLite and syncs atomic disk snapshot."""
        now = time.time()
        val_str = json.dumps(settings, ensure_ascii=False)

        def _write_db() -> bool:
            conn = self._get_db()
            try:
                conn.execute(
                    """
                    INSERT INTO settings (key, val, updated_at)
                    VALUES ('global', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=excluded.updated_at
                    """,
                    (val_str, now),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('global_settings.json', ?, ?)",
                    (val_str, now),
                )
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error saving settings to SQLite: {e}")
                return False
            finally:
                conn.close()

        ok = await asyncio.to_thread(_write_db)
        if ok:
            await asyncio.to_thread(self._atomic_write_file, self.settings_file, val_str)
        return ok

    load_farm_settings = load_settings
    save_farm_settings = save_settings
