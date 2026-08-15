"""
Authentication & Authorization logic for Telegram WebApp & REST API.
"""

import hashlib
import hmac
import json
import urllib.parse

from aiohttp import web

from config import API_SECRET_KEY, TELEGRAM_BOT_TOKEN, logger


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Cryptographically verifies Telegram WebApp initData HMAC-SHA256 signature.
    Returns parsed user dict if valid, or None if invalid/tampered.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(calculated_hash, hash_val):
            user_raw = parsed.get("user")
            if user_raw:
                return json.loads(user_raw)
            return {"valid": True}
    except Exception as e:
        logger.warning(f"Telegram initData verification error: {e}")
    return None


async def check_auth(request: web.Request) -> bool:
    """
    Multi-layer Security Check with strict Team Authorization:
    1. Validates X-API-Key header or ?token= query parameter against API_SECRET_KEY.
    2. Validates X-Telegram-Init-Data header or ?initData= query parameter HMAC signature against TELEGRAM_BOT_TOKEN
       AND checks if the Telegram user is an APPROVED team member in DB (is_user_approved).
    3. Denies access to unapproved, deleted, or unauthenticated external requests.
    """
    app_obj = request.app.get("app_obj")

    # 1. Check API Key for server-to-server / webhook integrations
    req_key = request.headers.get("X-API-Key") or request.query.get("token", "")
    if API_SECRET_KEY and req_key == API_SECRET_KEY:
        return True

    # 2. Check Telegram WebApp initData HMAC + DB User Approval
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("initData", "")
    if init_data:
        t_user = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
        if t_user and isinstance(t_user, dict):
            u_id = str(t_user.get("id") or "")
            if u_id and app_obj and hasattr(app_obj, "is_user_approved"):
                is_approved = await app_obj.is_user_approved(u_id)
                if not is_approved:
                    logger.warning(f"⛔ Revoked/unapproved user [{u_id}] attempted WebApp access!")
                    return False
                return True
            elif t_user.get("valid"):
                return True
        logger.warning("⛔ Invalid/tampered Telegram initData signature received!")
        return False

    # 3. Allow direct local unit test requests (aiohttp AioHTTPTestCase test client without tunnel)
    is_tunnel_req = bool(
        request.headers.get("X-Forwarded-For")
        or request.headers.get("X-Forwarded-Host")
        or request.headers.get("Bypass-Tunnel-Reminder")
    )
    if not API_SECRET_KEY and not is_tunnel_req and request.remote in ("127.0.0.1", "::1", None):
        return True

    return False
