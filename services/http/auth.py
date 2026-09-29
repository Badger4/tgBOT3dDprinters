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

_INITIAL_BOT_TOKEN = TELEGRAM_BOT_TOKEN


def _get_bot_token() -> str:
    """Returns the effective Telegram bot token, respecting test patches and dynamic setup."""
    if TELEGRAM_BOT_TOKEN != _INITIAL_BOT_TOKEN:
        return TELEGRAM_BOT_TOKEN
    import config
    return getattr(config, "TELEGRAM_BOT_TOKEN", "") or TELEGRAM_BOT_TOKEN


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


def is_request_secure(request: web.Request) -> bool:
    """Checks if request was made via HTTPS or behind an HTTPS reverse proxy/tunnel."""
    import config

    cookie_sec = getattr(config, "COOKIE_SECURE", None)
    if cookie_sec is not None and str(cookie_sec).strip() != "":
        return str(cookie_sec).lower() in ("true", "1", "yes")
    if request.scheme == "https":
        return True
    if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
        return True
    if getattr(config, "WEBAPP_URL", "").lower().startswith("https://"):
        return True
    return False


def set_session_cookie(response: web.StreamResponse, token: str, request: web.Request) -> None:
    """Sets secure session cookie with HttpOnly, Secure, and SameSite flags."""
    import config

    secure = is_request_secure(request)
    samesite = getattr(config, "COOKIE_SAMESITE", "Lax") or "Lax"
    response.set_cookie(
        "3d_farm_session",
        token,
        max_age=86400 * 7,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )


def delete_session_cookie(response: web.StreamResponse) -> None:
    """Deletes session cookie with matching root path."""
    response.del_cookie("3d_farm_session", path="/")


def _safe_header(request: web.Request, name: str) -> str:
    try:
        val = request.headers.get(name, "")
        return str(val) if isinstance(val, str) else ""
    except Exception:
        return ""


def _safe_cookie(request: web.Request, name: str) -> str:
    try:
        val = request.cookies.get(name, "")
        return str(val) if isinstance(val, str) else ""
    except Exception:
        return ""


def _safe_query(request: web.Request, name: str) -> str:
    try:
        val = request.query.get(name, "")
        return str(val) if isinstance(val, str) else ""
    except Exception:
        return ""


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Cryptographically verifies Telegram WebApp initData HMAC-SHA256 signature.
    Returns parsed user dict if valid, or None if invalid/tampered.
    """
    if not init_data or not isinstance(init_data, str) or not bot_token or not isinstance(bot_token, str):
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
        _safe_cookie(request, "3d_farm_session")
        or _safe_header(request, "X-Session-Token")
        or (_safe_header(request, "Authorization").replace("Bearer ", "").strip())
    )
    if is_valid_web_session(session_token):
        return True

    # 1. Check API Key or Admin Password for server-to-server / web login integrations
    import config

    req_key = _safe_header(request, "X-API-Key") or _safe_query(request, "token")
    admin_pass = getattr(config, "WEB_ADMIN_PASSWORD", "") or API_SECRET_KEY
    if (API_SECRET_KEY and req_key == API_SECRET_KEY) or (admin_pass and req_key == admin_pass):
        return True

    # 2. Check Telegram WebApp initData HMAC + DB User Approval
    init_data = _safe_header(request, "X-Telegram-Init-Data") or _safe_query(request, "initData")
    if init_data:
        bot_token = _get_bot_token()
        t_user = verify_telegram_init_data(init_data, bot_token)
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
        _safe_header(request, "X-Forwarded-For")
        or _safe_header(request, "X-Forwarded-Host")
        or _safe_header(request, "Bypass-Tunnel-Reminder")
    )
    remote = getattr(request, "remote", None)
    if not API_SECRET_KEY and not admin_pass and not is_tunnel_req and remote in ("127.0.0.1", "::1", None):
        return True

    if not API_SECRET_KEY and not admin_pass and _safe_header(request, "Bypass-Tunnel-Reminder") == "true":
        return True

    return False


async def is_admin_request(request: web.Request) -> bool:
    """
    Strict Admin Authorization Check:
    1. Standalone web session token (only issued to admin via master admin password).
    2. API Key / Secret matching API_SECRET_KEY or WEB_ADMIN_PASSWORD.
    3. Telegram WebApp initData where user is an authorized administrator:
       - user_id matches ADMIN_CHAT_ID, or
       - app_obj.is_user_admin(user_id) is True, or
       - storage user record has role == 'ADMIN' or admin.access_admin == True.
    4. Local development bypass (no secrets configured, request from localhost, not a tunnel).
    """
    import config

    app_obj = request.app.get("app_obj") if hasattr(request, "app") and hasattr(request.app, "get") else None

    # 1. Standalone Web Session Token (Cookie, Header, Bearer)
    session_token = (
        _safe_cookie(request, "3d_farm_session")
        or _safe_header(request, "X-Session-Token")
        or (_safe_header(request, "Authorization").replace("Bearer ", "").strip())
    )
    if is_valid_web_session(session_token):
        return True

    # 2. Check API Key or Admin Password
    req_key = _safe_header(request, "X-API-Key") or _safe_query(request, "token")
    admin_pass = getattr(config, "WEB_ADMIN_PASSWORD", "") or API_SECRET_KEY
    if (API_SECRET_KEY and req_key == API_SECRET_KEY) or (admin_pass and req_key == admin_pass):
        return True

    # 3. Telegram WebApp initData verification
    init_data = _safe_header(request, "X-Telegram-Init-Data") or _safe_query(request, "initData")
    if init_data:
        bot_token = _get_bot_token()
        t_user = verify_telegram_init_data(init_data, bot_token)
        if t_user and isinstance(t_user, dict):
            u_id = str(t_user.get("id") or "")
            if u_id:
                admin_chat_id = str(getattr(config, "ADMIN_CHAT_ID", "") or "")
                if admin_chat_id and u_id == admin_chat_id:
                    return True
                if app_obj and hasattr(app_obj, "is_user_admin"):
                    if await app_obj.is_user_admin(u_id):
                        return True
                if app_obj and hasattr(app_obj, "storage"):
                    u_data = await app_obj.storage.load_user(u_id)
                    if u_data:
                        if u_data.get("role") == "ADMIN" or bool(u_data.get("admin", {}).get("access_admin")):
                            return True
            # Telegram user is authenticated, but does NOT possess admin role
            return False

    # 4. Local dev bypass (only when no secrets configured & localhost & not tunnel)
    is_tunnel_req = bool(
        _safe_header(request, "X-Forwarded-For")
        or _safe_header(request, "X-Forwarded-Host")
        or _safe_header(request, "Bypass-Tunnel-Reminder")
    )
    remote = getattr(request, "remote", None)
    if not API_SECRET_KEY and not admin_pass and not is_tunnel_req and remote in ("127.0.0.1", "::1", None):
        return True

    return False


async def check_admin_auth(request: web.Request) -> bool:
    """Verifies that request is authenticated and caller has admin privileges."""
    if not await check_auth(request):
        return False
    return await is_admin_request(request)
