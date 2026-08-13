"""
SQLite-backed persistence manager with WAL mode, optimized for Raspberry Pi MicroSD flash card longevity.
Provides 100% backward-compatible async JSON/User interface while eliminating disk flash wear.
"""
import json
import time
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, cast

import aiofiles
from config import logger, ADMIN_CHAT_ID

class StorageManager:
    """Handles async persistence backed by SQLite with WAL mode to protect SD cards from flash wear."""
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.users_dir = base_dir / "users"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.base_dir / "printer_farm.db"
        self.printers_file = self.base_dir / "printers.json"
        self.settings_file = self.base_dir / "global_settings.json"
        self.spools_file = self.base_dir / "spools.json"
        self.history_file = self.base_dir / "history.json"
        self._file_locks: Dict[Path, asyncio.Lock] = {}

        self._init_db()

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
                conn = sqlite3.connect(self.db_path, timeout=20.0)
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
                async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
                    val_str = json.dumps(data, ensure_ascii=False)
                    now = time.time()
                    def _save_imported() -> None:
                        conn = sqlite3.connect(self.db_path, timeout=20.0)
                        try:
                            conn.execute(
                                "INSERT INTO kv_store (key, val, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=excluded.updated_at",
                                (key, val_str, now)
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
                conn = sqlite3.connect(self.db_path, timeout=20.0)
                try:
                    conn.execute(
                        "INSERT INTO kv_store (key, val, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET val=excluded.val, updated_at=excluded.updated_at",
                        (key, val_str, now)
                    )
                    conn.commit()
                    return True
                except Exception as e:
                    logger.error(f"SQLite save_json error for {key}: {e}")
                    return False
                finally:
                    conn.close()

            return await asyncio.to_thread(_write_db)

    async def load_user(self, user_id: str) -> Dict[str, Any]:
        user_id_str = str(user_id)

        def _get_user_db() -> Optional[Dict[str, Any]]:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                cur = conn.execute("SELECT data FROM users WHERE user_id = ?", (user_id_str,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else None
            finally:
                conn.close()

        db_user = await asyncio.to_thread(_get_user_db)
        if db_user:
            if user_id_str == str(ADMIN_CHAT_ID):
                db_user["is_approved"] = True
                if "admin" not in db_user:
                    db_user["admin"] = {}
                db_user["admin"]["access_admin"] = True
            return db_user

        # Fallback & Migration from legacy files
        legacy_kas = self.base_dir / f"user_{user_id_str}.kas"
        user_json = self.users_dir / f"user_{user_id_str}.json"
        target_path = user_json if user_json.exists() else (legacy_kas if legacy_kas.exists() else user_json)

        default_user = {
            "user_id": user_id_str,
            "is_approved": (user_id_str == str(ADMIN_CHAT_ID)),
            "created_at": time.time(),
            "admin": {"access_admin": (user_id_str == str(ADMIN_CHAT_ID))},
            "personal": {},
            "notify": {
                "start": True,
                "finish": True,
                "pause": True,
                "min_time_to_end": 0,
                "min_filament": 0,
                "notified_filament": False,
                "notified_time": False
            },
            "state": "idle",
            "context_data": {}
        }

        user_data = default_user
        if target_path.exists():
            try:
                async with aiofiles.open(target_path, mode='r', encoding='utf-8') as f:
                    user_data = json.loads(await f.read())
            except Exception as e:
                logger.error(f"Error reading legacy user file {target_path}: {e}")


        user_data["user_id"] = user_id_str


        if user_id_str == str(ADMIN_CHAT_ID):
            user_data["is_approved"] = True
            if not isinstance(user_data.get("admin"), dict):
                user_data["admin"] = {}
            admin_dict = cast(Dict[str, Any], user_data["admin"])
            admin_dict["access_admin"] = True



        await self.save_user(user_data)
        if legacy_kas.exists():
            legacy_kas.unlink(missing_ok=True)
        return user_data

    async def save_user(self, user_data: Dict[str, Any]) -> None:
        user_id_str = str(user_data["user_id"])
        val_str = json.dumps(user_data, ensure_ascii=False)
        now = time.time()

        def _save_user_db() -> None:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                conn.execute(
                    "INSERT INTO users (user_id, data, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                    (user_id_str, val_str, now)
                )
                conn.commit()
            except Exception as e:
                logger.error(f"SQLite save_user error for {user_id_str}: {e}")
            finally:
                conn.close()

        await asyncio.to_thread(_save_user_db)

    async def delete_user(self, user_id: str) -> bool:
        """Permanently deletes a user from SQLite database and legacy files."""
        user_id_str = str(user_id)
        if user_id_str == str(ADMIN_CHAT_ID):
            logger.warning(f"Attempted to delete main admin {user_id_str}")
            return False

        def _delete_db() -> bool:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                conn.execute("DELETE FROM users WHERE user_id = ?", (user_id_str,))
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"SQLite delete_user error for {user_id_str}: {e}")
                return False
            finally:
                conn.close()

        res = await asyncio.to_thread(_delete_db)

        # Remove legacy files if present
        for f in [self.base_dir / f"user_{user_id_str}.kas", self.base_dir / f"user_{user_id_str}.json", self.users_dir / f"user_{user_id_str}.json"]:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        return bool(res)

    async def load_all_users(self) -> Dict[str, Dict[str, Any]]:
        def _get_all_db_users() -> Dict[str, Dict[str, Any]]:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                cur = conn.execute("SELECT user_id, data FROM users")
                return {row[0]: json.loads(row[1]) for row in cur.fetchall()}
            finally:
                conn.close()


        users = await asyncio.to_thread(_get_all_db_users)
        
        # Check for unmigrated disk files
        all_files = list(self.base_dir.glob("user_*.kas")) + list(self.base_dir.glob("user_*.json")) + list(self.users_dir.glob("user_*.json"))
        for file in all_files:
            uid = file.stem.replace("user_", "")
            if uid not in users:
                users[uid] = await self.load_user(uid)

        return users

    async def load_spools(self) -> Dict[str, Dict[str, Any]]:
        default_spools = {
            "spool_1": {
                "id": "spool_1",
                "name": "Sunlu PLA Black",
                "brand": "Sunlu",
                "type": "PLA",
                "color": "Black",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 650.0
            },
            "spool_2": {
                "id": "spool_2",
                "name": "eSUN PETG Grey",
                "brand": "eSUN",
                "type": "PETG",
                "color": "Grey",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 700.0
            }
        }
        return await self.load_json(self.spools_file, default_spools)

    async def save_spools(self, spools: Dict[str, Dict[str, Any]]) -> bool:
        return await self.save_json(self.spools_file, spools)

    async def load_history(self) -> List[Dict[str, Any]]:
        return await self.load_json(self.history_file, [])

    async def add_history_entry(self, entry: Dict[str, Any]) -> bool:
        history = await self.load_history()
        history.append(entry)
        if len(history) > 500:
            history = history[-500:]
        return await self.save_json(self.history_file, history)
