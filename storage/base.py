"""
Base persistence layer backed by SQLite with WAL mode, optimized for flash storage.
Provides ACID transactions, single source of truth (SSOT), and crash-proof atomic file snapshots.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiofiles

from config import logger


class BaseStorage:
    """Provides thread-safe, async SQLite-backed persistence with WAL mode and atomic disk snapshots."""

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.users_dir = self.base_dir / "users"
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
        self.last_sliced_weight_file = self.base_dir / "last_sliced_weight.json"
        self.contexts_file = self.base_dir / "active_print_contexts.json"

        self._file_locks: dict[Path, asyncio.Lock] = {}
        self._tx_locks: dict[str, asyncio.Lock] = {}

        self._init_db()

    @asynccontextmanager
    async def transaction_lock(self, lock_key: str) -> AsyncIterator[None]:
        if lock_key not in self._tx_locks:
            self._tx_locks[lock_key] = asyncio.Lock()
        async with self._tx_locks[lock_key]:
            yield

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Initializes SQLite schema with WAL mode and domain tables for complete SSOT."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

            # 1. Generic Key-Value store (retained for backward-compatibility and migration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_store (
                    key TEXT PRIMARY KEY,
                    val TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 2. Users and RBAC
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 3. Printers Fleet
            conn.execute("""
                CREATE TABLE IF NOT EXISTS printers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    model TEXT,
                    ip TEXT,
                    access_code TEXT,
                    serial TEXT,
                    has_ams INTEGER DEFAULT 0,
                    config_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 4. Filament Spools Warehouse
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spools (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    brand TEXT,
                    type TEXT,
                    color TEXT,
                    remaining_grams REAL NOT NULL,
                    total_grams REAL NOT NULL,
                    price_uah REAL NOT NULL,
                    assigned_printer_id TEXT,
                    assigned_slot_key TEXT,
                    is_active INTEGER DEFAULT 1,
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_spools_printer ON spools(assigned_printer_id);")

            # 5. Warehouse Movements Audit Log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS warehouse_movements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    spool_id TEXT NOT NULL,
                    spool_name TEXT,
                    movement_type TEXT NOT NULL,
                    weight_delta REAL NOT NULL,
                    final_weight REAL NOT NULL,
                    reason TEXT,
                    printer_id TEXT,
                    user_id TEXT,
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_movements_spool ON warehouse_movements(spool_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_movements_ts ON warehouse_movements(timestamp);")

            # 6. Active Print Contexts
            conn.execute("""
                CREATE TABLE IF NOT EXISTS print_contexts (
                    printer_id TEXT PRIMARY KEY,
                    subtask_name TEXT,
                    spool_fingerprint TEXT,
                    saved_layer INTEGER DEFAULT 0,
                    progress_pct INTEGER DEFAULT 0,
                    job_grams REAL DEFAULT 0.0,
                    job_deducted INTEGER DEFAULT 1,
                    context_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 7. Sliced Weight and 3MF Cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS slice_cache (
                    key TEXT PRIMARY KEY,
                    filename TEXT,
                    weight REAL DEFAULT 0.0,
                    time_mins REAL DEFAULT 0.0,
                    objects_json TEXT,
                    updated_at REAL NOT NULL
                );
            """)

            # 8. Finished Printed Parts Catalog
            conn.execute("""
                CREATE TABLE IF NOT EXISTS parts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    count INTEGER DEFAULT 0,
                    quantity INTEGER DEFAULT 0,
                    image TEXT,
                    three_mf TEXT,
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 9. Commercial Pricing Presets
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commercial_presets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

            # 10. Completed Print Jobs History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS print_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    printer_id TEXT,
                    printer_name TEXT,
                    subtask_name TEXT,
                    weight_g REAL,
                    cost_uah REAL,
                    status TEXT,
                    data_json TEXT NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_ts ON print_history(timestamp);")

            # 11. Farm Settings
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    val TEXT NOT NULL,
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

    def _atomic_write_file(self, path: Path, content: str) -> None:
        """Atomically writes content to a file via a temporary file + replace to prevent corruption."""
        tmp_path = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}.{time.time()}")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            for attempt in range(5):
                try:
                    os.replace(tmp_path, path)
                    return
                except (PermissionError, OSError):
                    if attempt < 4:
                        time.sleep(0.005)
                    else:
                        raise
        except Exception as e:
            logger.warning(f"Error syncing atomic file replica for {path}: {e}")
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

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
        key = path.name
        if key in ("parts.json", "parts_warehouse.json") and hasattr(self, "save_parts"):
            return await self.save_parts(data)
        if key == "spools.json" and hasattr(self, "save_spools"):
            return await self.save_spools(data)
        if key == "printers.json" and hasattr(self, "save_printers"):
            return await self.save_printers(data)
        if key in ("commercial_presets.json", "presets.json") and hasattr(self, "save_presets"):
            return await self.save_presets(data)
        if key in ("global_settings.json", "farm_settings.json") and hasattr(self, "save_settings"):
            return await self.save_settings(data)

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

            ok = await asyncio.to_thread(_write_db)
            if ok:
                await asyncio.to_thread(self._atomic_write_file, path, val_str)
            return ok

    # =========================================================================
    # Sliced Weight & 3MF Job Metadata Cache (SSOT + atomic replica)
    # =========================================================================
    def get_sliced_weight_cache_sync(self) -> dict[str, Any] | None:
        """Synchronously retrieves the latest sliced weight cache (for MQTT thread)."""
        conn = self._get_db()
        try:
            cur = conn.execute("SELECT objects_json FROM slice_cache WHERE key = 'latest'")
            row = cur.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Error reading slice_cache from DB: {e}")
        finally:
            conn.close()

        # Fallback to last_sliced_weight.json on disk
        if self.last_sliced_weight_file.exists():
            try:
                data = json.loads(self.last_sliced_weight_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    async def get_sliced_weight_cache(self) -> dict[str, Any] | None:
        """Async retrieval of latest sliced weight cache."""
        return await asyncio.to_thread(self.get_sliced_weight_cache_sync)

    def set_sliced_weight_cache_sync(self, data: dict[str, Any]) -> bool:
        """Synchronously persists sliced weight cache to SQLite and atomic disk replica."""
        now = time.time()
        val_str = json.dumps(data, ensure_ascii=False)
        filename = str(data.get("filename") or data.get("path") or "")
        weight = float(data.get("weight", 0.0))
        time_mins = float(data.get("time_mins", 0.0))

        conn = self._get_db()
        try:
            conn.execute(
                """
                INSERT INTO slice_cache (key, filename, weight, time_mins, objects_json, updated_at)
                VALUES ('latest', ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    filename=excluded.filename,
                    weight=excluded.weight,
                    time_mins=excluded.time_mins,
                    objects_json=excluded.objects_json,
                    updated_at=excluded.updated_at
                """,
                (filename, weight, time_mins, val_str, now),
            )
            # Also mirror to kv_store for legacy lookups
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, val, updated_at) VALUES ('last_sliced_weight.json', ?, ?)",
                (val_str, now),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error writing slice_cache to DB: {e}")
            return False
        finally:
            conn.close()

        # Atomically flush to disk replica
        self._atomic_write_file(self.last_sliced_weight_file, val_str)
        return True

    async def set_sliced_weight_cache(self, data: dict[str, Any]) -> bool:
        """Async persistence of sliced weight cache."""
        return await asyncio.to_thread(self.set_sliced_weight_cache_sync, data)
