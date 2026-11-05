"""
User settings and RBAC administration HTTP endpoints.
"""

from __future__ import annotations

import html
import json
import time
from typing import Any

from aiohttp import web

import config
from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN, logger
from services.http.auth import check_auth, is_admin_request, verify_telegram_init_data

def get_authenticated_user_id(request: web.Request) -> str | None:
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("initData", "")
    if init_data:
        bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or TELEGRAM_BOT_TOKEN
        t_user = verify_telegram_init_data(init_data, bot_token)
        if t_user and isinstance(t_user, dict):
            u_id = str(t_user.get("id") or "")
            if u_id:
                return u_id
    return None


async def handle_get_user_settings(request: web.Request) -> web.Response:
    """GET /api/user/settings - Get user-specific notification settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    u_id = get_authenticated_user_id(request)

    user_notify = {
        "start": True,
        "finish": True,
        "pause": True,
        "hms": True,
        "remind_clear": True,
        "min_time_to_end": 0,
        "min_filament": 0,
    }
    user_info = {"id": u_id or "", "role": "USER", "approved": True}
    user_lang = "uk"

    is_admin = False
    if u_id and hasattr(app_obj, "storage"):
        user = await app_obj.storage.load_user(u_id)
        if user:
            user_notify.update(user.get("notify", {}))
            is_admin = (str(u_id) == str(ADMIN_CHAT_ID)) or bool(user.get("admin", {}).get("access_admin")) or user.get("role") == "ADMIN"
            user_info["role"] = "ADMIN" if is_admin else "USER"
            user_info["is_admin"] = is_admin
            user_info["approved"] = user.get("approved", True)
            user_lang = user.get("language", "uk")
    else:
        is_admin = True
        user_info["role"] = "ADMIN"
        user_info["is_admin"] = True

    return web.json_response({"notify": user_notify, "user": user_info, "language": user_lang})


async def handle_update_user_settings(request: web.Request) -> web.Response:
    """POST /api/user/settings - Update user-specific notification settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    u_id = get_authenticated_user_id(request)
    try:
        data = await request.json()
        notify_data = data.get("notify", {})
        new_lang = data.get("language")

        if u_id and hasattr(app_obj, "storage"):
            user = await app_obj.storage.load_user(u_id)
            if not isinstance(user.get("notify"), dict):
                user["notify"] = {}
            if notify_data:
                user["notify"].update(notify_data)
            if new_lang and str(new_lang).lower() in ["uk", "en"]:
                user["language"] = str(new_lang).lower()
            await app_obj.storage.save_user(user)
            return web.json_response({"status": "ok", "notify": user["notify"], "language": user.get("language", "uk")})

        return web.json_response({"status": "ok", "notify": notify_data, "language": new_lang or "uk"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_get_users(request: web.Request) -> web.Response:
    """GET /api/users - Admin list of registered Telegram users."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not await is_admin_request(request):
        return web.json_response({"error": "Forbidden: Admin access required"}, status=403)

    app_obj = request.app["app_obj"]
    users = {}
    if hasattr(app_obj, "storage"):
        users = await app_obj.storage.load_all_users()

    user_list = []
    for uid, udata in users.items():
        uid_str = str(uid)
        is_admin = (uid_str == str(ADMIN_CHAT_ID)) or bool(udata.get("admin", {}).get("access_admin"))

        # Strictly default to False for non-admin users if is_approved is missing or False
        raw_approved = udata.get("is_approved")
        if raw_approved is None:
            raw_approved = udata.get("approved")
        is_approved = is_admin or (bool(raw_approved) if raw_approved is not None else False)

        first_name = str(udata.get("personal", {}).get("first_name") or udata.get("first_name") or "").strip()
        last_name = str(udata.get("personal", {}).get("last_name") or udata.get("last_name") or "").strip()
        username = str(udata.get("personal", {}).get("username") or udata.get("username") or "").strip()

        full_name = f"{first_name} {last_name}".strip() or f"Користувач {uid_str}"
        display_name = f"{full_name} (@{username})" if username else full_name

        user_list.append({
            "id": uid_str,
            "user_id": uid_str,
            "first_name": first_name,
            "username": username,
            "name": display_name,
            "role": udata.get("role") or ("ADMIN" if is_admin else "USER"),
            "approved": is_approved,
            "is_approved": is_approved,
            "created_at": udata.get("created_at", 0),
        })

    return web.json_response({"users": user_list})


async def handle_update_user_access(request: web.Request) -> web.Response:
    """POST /api/users/access - Admin update user approval or role."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not await is_admin_request(request):
        return web.json_response({"error": "Forbidden: Admin access required"}, status=403)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        target_id = str(data.get("user_id", "")).strip()
        if not target_id:
            return web.json_response({"error": "Missing user_id"}, status=400)

        if hasattr(app_obj, "storage"):
            user = await app_obj.storage.load_user(target_id)
            if "approved" in data:
                user["approved"] = bool(data["approved"])
                user["is_approved"] = bool(data["approved"])
            if "role" in data and data["role"] in ["ADMIN", "USER"]:
                user["role"] = data["role"]
                if "admin" not in user or not isinstance(user["admin"], dict):
                    user["admin"] = {}
                user["admin"]["access_admin"] = (data["role"] == "ADMIN")
            await app_obj.storage.save_user(user)
            return web.json_response({"status": "ok", "user": user})

        return web.json_response({"error": "Storage unresolvable"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_user(request: web.Request) -> web.Response:
    """POST /api/users/delete or DELETE /api/users/{id} - Admin delete a user/bot account."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    if not await is_admin_request(request):
        return web.json_response({"error": "Forbidden: Admin access required"}, status=403)

    app_obj = request.app["app_obj"]
    try:
        target_id = request.match_info.get("id", "").strip()
        if not target_id:
            try:
                data = await request.json()
                target_id = str(data.get("user_id", "")).strip()
            except Exception:
                pass

        if not target_id:
            return web.json_response({"error": "Missing user_id"}, status=400)

        if target_id == str(ADMIN_CHAT_ID):
            return web.json_response({"error": "Cannot delete main admin"}, status=400)

        if hasattr(app_obj, "storage"):
            deleted = await app_obj.storage.delete_user(target_id)
            if deleted:
                return web.json_response({"status": "ok", "deleted_user_id": target_id})
            return web.json_response({"error": "User not found"}, status=404)

        return web.json_response({"error": "Storage unresolvable"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

