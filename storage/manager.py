"""
Async JSON persistence manager with per-file mutex locks to prevent race conditions.
"""
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import aiofiles
from config import logger, ADMIN_CHAT_ID

class StorageManager:
    """Handles async JSON persistence for users, printers, and global settings with thread-safe locks."""
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.users_dir = base_dir / "users"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.users_dir.mkdir(parents=True, exist_ok=True)

        self.printers_file = self.base_dir / "printers.json"
        self.settings_file = self.base_dir / "global_settings.json"
        self.spools_file = self.base_dir / "spools.json"
        self.history_file = self.base_dir / "history.json"
        self._file_locks: Dict[Path, asyncio.Lock] = {}

    def _get_lock(self, path: Path) -> asyncio.Lock:
        if path not in self._file_locks:
            self._file_locks[path] = asyncio.Lock()
        return self._file_locks[path]

    async def load_json(self, path: Path, default: Any) -> Any:
        lock = self._get_lock(path)
        async with lock:
            if not path.exists():
                return default
            try:
                async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Error reading JSON {path}: {e}")
                return default

    async def save_json(self, path: Path, data: Any) -> bool:
        lock = self._get_lock(path)
        async with lock:
            try:
                tmp_path = path.with_suffix(f"{path.suffix}.tmp")
                async with aiofiles.open(tmp_path, mode='w', encoding='utf-8') as f:
                    await f.write(json.dumps(data, indent=2, ensure_ascii=False))
                tmp_path.replace(path)
                return True
            except Exception as e:
                logger.error(f"Error writing JSON {path}: {e}")
                return False

    async def load_user(self, user_id: str) -> Dict[str, Any]:
        user_id_str = str(user_id)
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
        user_data = await self.load_json(target_path, default_user)
        user_data["user_id"] = user_id_str

        if user_id_str == str(ADMIN_CHAT_ID):
            user_data["is_approved"] = True
            if "admin" not in user_data:
                user_data["admin"] = {}
            user_data["admin"]["access_admin"] = True

        return user_data

    async def save_user(self, user_data: Dict[str, Any]):
        user_id = str(user_data["user_id"])
        user_path = self.users_dir / f"user_{user_id}.json"
        await self.save_json(user_path, user_data)

    async def load_all_users(self) -> Dict[str, Dict[str, Any]]:
        users = {}
        all_files = list(self.base_dir.glob("user_*.kas")) + list(self.base_dir.glob("user_*.json")) + list(self.users_dir.glob("user_*.json"))
        for file in all_files:
            user_id = file.stem.replace("user_", "")
            if user_id not in users:
                users[user_id] = await self.load_user(user_id)
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
