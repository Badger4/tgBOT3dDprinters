"""
Base persistence layer backed by SQLite with WAL mode, optimized for flash storage.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiofiles

from config import logger


class BaseStorage:
    """Provides thread-safe, async SQLite-backed persistence with WAL mode."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.users_dir = base_dir / "users"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.base_dir / "printer_farm.db"
        self.printers_file = self.base_dir / "printers.json"
        self.settings_file = self.base_dir / "global_settings.json"
        self.spools_file = self.base_dir / "spools.json"
        self.parts_file = self.base_dir / "parts.json"
        self.presets_file = self.base_dir / "commercial_presets.json"
        self.history_file = self.base_dir / "history.json"
        self.movements_file = self.base_dir / "warehouse_movements.json"

        self._file_locks: dict[Path, asyncio.Lock] = {}
        self._tx_locks: dict[str, asyncio.Lock] = {}
        self._kv_cache: dict[str, Any] = {}
        self._user_cache: dict[str, Any] = {}

        self._init_db()

    @asynccontextmanager
    async def transaction_lock(self, lock_key: str) -> AsyncIterator[None]:
        if lock_key not in self._tx_locks:
            self._tx_locks[lock_key] = asyncio.Lock()
        async with self._tx_locks[lock_key]:
            yield

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Initializes SQLite schema with WAL mode for SD card flash protection."""
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    val TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_lock(self, path: Path) -> asyncio.Lock:
        if path not in self._file_locks:
            self._file_locks[path] = asyncio.Lock()
        return self._file_locks[path]

    async def load_json(self, path: Path, default: Any) -> Any:
        lock = self._get_lock(path)
        async with lock:
            key = path.name

            def _query_db() -> Any:
                conn = self._get_db()
                try:
                    cur = conn.execute("SELECT val FROM kv_store WHERE key = ?", (key,))
                    row = cur.fetchone()
                    return json.loads(row[0]) if row else None
                finally:
                    conn.close()

            db_val = await asyncio.to_thread(_query_db)
            if db_val is not None:
                return db_val

            # Fallback to filesystem JSON file if DB key does not exist yet
            if not path.exists():
                bak_path = path.with_suffix(f"{path.suffix}.bak")
                if bak_path.exists():
                    path = bak_path
                else:
                    return default
            try:
                async with aiofiles.open(path, encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                    val_str = json.dumps(data, ensure_ascii=False)
                    now = time.time()

                    def _save_imported() -> None:
                        conn = self._get_db()
                        try:
                            conn.execute(
                                "INSERT INTO kv_store (key, val, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=excluded.updated_at",
                                (key, val_str, now),
                            )
                            conn.commit()
                        finally:
                            conn.close()

                    await asyncio.to_thread(_save_imported)
                    return data
            except Exception as e:
                logger.error(f"Error reading JSON {path}: {e}")
                return default

    async def save_json(self, path: Path, data: Any) -> bool:
        lock = self._get_lock(path)
        async with lock:
            key = path.name
            val_str = json.dumps(data, ensure_ascii=False)
            now = time.time()

            def _write_db() -> bool:
                conn = self._get_db()
                try:
                    conn.execute(
                        "INSERT INTO kv_store (key, val, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=excluded.updated_at",
                        (key, val_str, now),
                    )
                    conn.commit()
                    return True
                except Exception as e:
                    logger.error(f"SQLite save_json error for {key}: {e}")
                    return False
                finally:
                    conn.close()

            return await asyncio.to_thread(_write_db)
