"""
Authentication & Authorization logic for Telegram WebApp & REST API.
"""

import hashlib
import hmac
import json
import urllib.parse

from aiohttp import web

import secrets
import time

from config import API_SECRET_KEY, TELEGRAM_BOT_TOKEN, logger

# Active web sessions dict (token -> expiry timestamp)
ACTIVE_WEB_SESSIONS: dict[str, float] = {}


def create_web_session(expiry_seconds: int = 86400 * 7) -> str:
    """Generates a secure web session token valid for expiry_seconds (default 7 days)."""
    token = secrets.token_hex(32)
    ACTIVE_WEB_SESSIONS[token] = time.time() + expiry_seconds
    return token


def is_valid_web_session(token: str | None) -> bool:
    """Verifies if a web session token is active and unexpired."""
    if not token or token not in ACTIVE_WEB_SESSIONS:
        return False
    if time.time() > ACTIVE_WEB_SESSIONS[token]:
        ACTIVE_WEB_SESSIONS.pop(token, None)
        return False
    return True


def revoke_web_session(token: str | None) -> None:
    """Revokes an active web session token."""
    if token and token in ACTIVE_WEB_SESSIONS:
        ACTIVE_WEB_SESSIONS.pop(token, None)


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
    1. Validates Standalone Web Sessions (Cookie / Header).
    2. Validates X-API-Key header or ?token= query parameter against API_SECRET_KEY or WEB_ADMIN_PASSWORD.
    3. Validates X-Telegram-Init-Data header or ?initData= query parameter HMAC signature against TELEGRAM_BOT_TOKEN.
    4. Denies access to unapproved, deleted, or unauthenticated external requests.
    """
    app_obj = request.app.get("app_obj")

    # 0. Check Standalone Web Session (Cookie / Header / Bearer)
    session_token = (
        request.cookies.get("3d_farm_session")
        or request.headers.get("X-Session-Token")
        or (request.headers.get("Authorization", "").replace("Bearer ", "").strip())
    )
    if is_valid_web_session(session_token):
        return True

    # 1. Check API Key or Admin Password for server-to-server / web login integrations
    import config

    req_key = request.headers.get("X-API-Key") or request.query.get("token", "")
    admin_pass = getattr(config, "WEB_ADMIN_PASSWORD", "") or API_SECRET_KEY
    if (API_SECRET_KEY and req_key == API_SECRET_KEY) or (admin_pass and req_key == admin_pass):
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

    # 3. Allow direct local unit test & local browser requests
    is_tunnel_req = bool(
        request.headers.get("X-Forwarded-For")
        or request.headers.get("X-Forwarded-Host")
        or request.headers.get("Bypass-Tunnel-Reminder")
    )
    if not API_SECRET_KEY and not admin_pass and not is_tunnel_req and request.remote in ("127.0.0.1", "::1", None):
        return True

    if not API_SECRET_KEY and not admin_pass and request.headers.get("Bypass-Tunnel-Reminder") == "true":
        return True

    return False
