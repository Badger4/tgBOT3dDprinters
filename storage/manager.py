"""
SQLite-backed persistence manager with WAL mode, optimized for Raspberry Pi MicroSD flash card longevity.
Provides 100% backward-compatible async JSON/User interface while eliminating disk flash wear.
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, cast

import aiofiles

from config import ADMIN_CHAT_ID, logger


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
        self.parts_file = self.base_dir / "parts.json"
        self.history_file = self.base_dir / "history.json"
        self.movements_file = self.base_dir / "warehouse_movements.json"
        self._file_locks: dict[Path, asyncio.Lock] = {}

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
                async with aiofiles.open(path, encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
                    val_str = json.dumps(data, ensure_ascii=False)
                    now = time.time()

                    def _save_imported() -> None:
                        conn = sqlite3.connect(self.db_path, timeout=20.0)
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
                conn = sqlite3.connect(self.db_path, timeout=20.0)
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

    async def load_user(self, user_id: str) -> dict[str, Any]:
        user_id_str = str(user_id)

        def _get_user_db() -> dict[str, Any] | None:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)
                cur = conn.execute("SELECT data FROM users WHERE user_id = ?", (user_id_str,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else None
            except Exception as e:
                logger.error(f"SQLite _get_user_db error for {user_id_str}: {e}")
                return None
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
                "notified_time": False,
            },
            "state": "idle",
            "context_data": {},
        }

        user_data = default_user
        if target_path.exists():
            try:
                async with aiofiles.open(target_path, encoding="utf-8") as f:
                    user_data = json.loads(await f.read())
            except Exception as e:
                logger.error(f"Error reading legacy user file {target_path}: {e}")

        user_data["user_id"] = user_id_str

        if user_id_str == str(ADMIN_CHAT_ID):
            user_data["is_approved"] = True
            if not isinstance(user_data.get("admin"), dict):
                user_data["admin"] = {}
            admin_dict = cast(dict[str, Any], user_data["admin"])
            admin_dict["access_admin"] = True

        await self.save_user(user_data)
        if legacy_kas.exists():
            legacy_kas.unlink(missing_ok=True)
        return user_data

    async def save_user(self, user_data: dict[str, Any]) -> None:
        user_id_str = str(user_data["user_id"])
        val_str = json.dumps(user_data, ensure_ascii=False)
        now = time.time()

        def _save_user_db() -> None:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)
                conn.execute(
                    "INSERT INTO users (user_id, data, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                    (user_id_str, val_str, now),
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
        for f in [
            self.base_dir / f"user_{user_id_str}.kas",
            self.base_dir / f"user_{user_id_str}.json",
            self.users_dir / f"user_{user_id_str}.json",
        ]:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        return bool(res)

    async def load_all_users(self) -> dict[str, dict[str, Any]]:
        def _get_all_db_users() -> dict[str, dict[str, Any]]:
            conn = sqlite3.connect(self.db_path, timeout=20.0)
            try:
                cur = conn.execute("SELECT user_id, data FROM users")
                return {row[0]: json.loads(row[1]) for row in cur.fetchall()}
            finally:
                conn.close()

        users = await asyncio.to_thread(_get_all_db_users)

        # Check for unmigrated disk files
        all_files = (
            list(self.base_dir.glob("user_*.kas"))
            + list(self.base_dir.glob("user_*.json"))
            + list(self.users_dir.glob("user_*.json"))
        )
        for file in all_files:
            uid = file.stem.replace("user_", "")
            if uid not in users:
                users[uid] = await self.load_user(uid)

        return users

    async def load_spools(self) -> dict[str, dict[str, Any]]:
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
        data = await self.load_json(self.spools_file, default_spools)
        raw_dict = {}
        if isinstance(data, list):
            raw_dict = {s["id"]: s for s in data if isinstance(s, dict) and "id" in s}
        elif isinstance(data, dict):
            raw_dict = data
        else:
            raw_dict = default_spools

        # Filter out depleted spools (remaining_grams <= 0.0)
        filtered = {}
        for s_id, s in raw_dict.items():
            if isinstance(s, dict):
                try:
                    rem_g = float(s.get("remaining_grams", 1000.0))
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    filtered[s_id] = s
        return filtered

    async def save_spools(self, spools: dict[str, dict[str, Any]]) -> bool:
        filtered = {}
        for s_id, s in spools.items():
            if isinstance(s, dict):
                try:
                    rem_g = float(s.get("remaining_grams", 1000.0))
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    filtered[s_id] = s
        return await self.save_json(self.spools_file, filtered)

    async def load_parts(self) -> dict[str, dict[str, Any]]:
        data = await self.load_json(self.parts_file, {})
        if isinstance(data, list):
            return {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
        if isinstance(data, dict):
            return data
        return {}

    async def save_parts(self, parts: dict[str, dict[str, Any]]) -> bool:
        return await self.save_json(self.parts_file, parts)

    async def load_spool_movements(self) -> list[dict[str, Any]]:
        """Loads warehouse movement audit history."""
        return await self.load_json(self.movements_file, [])

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
        """Records a spool weight movement / audit log entry."""
        movements = await self.load_spool_movements()
        now = time.time()
        entry = {
            "id": f"mov_{int(now * 1000)}",
            "timestamp": now,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "spool_id": spool_id,
            "spool_name": spool_name,
            "action": action,  # "print", "refill", "manual_edit", "write_off"
            "weight_change_g": round(float(weight_change_g), 2),
            "prev_weight_g": round(float(prev_weight_g), 2),
            "new_weight_g": round(float(new_weight_g), 2),
            "reason": reason or action,
            "user": user,
        }
        movements.append(entry)
        if len(movements) > 1000:
            movements = movements[-1000:]
        await self.save_json(self.movements_file, movements)
        logger.info(f"📦 Audit Log [{action}] for '{spool_name}' ({spool_id}): {weight_change_g:+.1f}g -> new: {new_weight_g:.1f}g ({reason})")
        return entry

    async def load_history(self) -> list[dict[str, Any]]:
        return await self.load_json(self.history_file, [])

    async def add_history_entry(self, entry: dict[str, Any]) -> bool:
        history = await self.load_history()
        p_name = entry.get("printer_name")
        sub_name = entry.get("subtask_name")
        ts = float(entry.get("timestamp", time.time()))

        for existing in history[-20:]:
            e_p_name = existing.get("printer_name")
            e_sub_name = existing.get("subtask_name")
            e_ts = float(existing.get("timestamp", 0.0))
            if e_p_name == p_name and e_sub_name == sub_name and abs(ts - e_ts) < 120:
                logger.info(f"🛡️ Skipped duplicate history entry for [{p_name}] - '{sub_name}'")
                return True

        history.append(entry)
        if len(history) > 500:
            history = history[-500:]
        return await self.save_json(self.history_file, history)

    async def clear_history(self) -> bool:
        """Clears all print history records."""
        return await self.save_json(self.history_file, [])

    async def delete_history_entry(self, timestamp: float) -> bool:
        """Deletes a single history record matching the given timestamp."""
        history = await self.load_history()
        filtered = [item for item in history if item.get("timestamp") != timestamp]
        return await self.save_json(self.history_file, filtered)

