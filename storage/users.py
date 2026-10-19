"""
Repository for Telegram bot users and RBAC permissions.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, cast

import aiofiles

from config import ADMIN_CHAT_ID, logger
from storage.base import BaseStorage


class UserRepository(BaseStorage):
    """Handles async persistence for user accounts and role-based access control."""

    async def load_user(self, user_id: str) -> dict[str, Any]:
        user_id_str = str(user_id)

        def _get_user_db() -> dict[str, Any] | None:
            conn = self._get_db()
            try:
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
        legacy_found = False
        if target_path.exists():
            try:
                async with aiofiles.open(target_path, encoding="utf-8") as f:
                    user_data = json.loads(await f.read())
                    legacy_found = True
            except Exception as e:
                logger.error(f"Error reading legacy user file {target_path}: {e}")

        user_data["user_id"] = user_id_str

        if user_id_str == str(ADMIN_CHAT_ID):
            user_data["is_approved"] = True
            if not isinstance(user_data.get("admin"), dict):
                user_data["admin"] = {}
            admin_dict = cast(dict[str, Any], user_data["admin"])
            admin_dict["access_admin"] = True

        if legacy_found or user_id_str == str(ADMIN_CHAT_ID):
            await self.save_user(user_data)
            if legacy_kas.exists():
                legacy_kas.unlink(missing_ok=True)
        return user_data

    async def save_user(self, user_data: dict[str, Any]) -> None:
        user_id_str = str(user_data["user_id"])
        val_str = json.dumps(user_data, ensure_ascii=False)
        now = time.time()

        def _save_user_db() -> None:
            conn = self._get_db()
            try:
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
            conn = self._get_db()
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
            conn = self._get_db()
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
