"""
Authentication & First-Launch Setup Wizard REST API endpoints for Standalone Web Access.
"""

from pathlib import Path
from aiohttp import web

import config
from config import update_env_key
from services.http.auth import create_web_session, is_valid_web_session, revoke_web_session

WEBAPP_DIR = Path(__file__).parent.parent.parent / "webapp"


def _is_setup_completed() -> bool:
    """Checks if first-launch setup has been completed."""
    has_pass = bool(getattr(config, "WEB_ADMIN_PASSWORD", "") or getattr(config, "API_SECRET_KEY", ""))
    has_bot = bool(getattr(config, "TELEGRAM_BOT_TOKEN", ""))
    return has_pass or has_bot


async def handle_serve_login(request: web.Request) -> web.StreamResponse:
    """GET /login - Serves standalone web login page."""
    login_file = WEBAPP_DIR / "login.html"
    if login_file.exists():
        return web.FileResponse(login_file)
    return web.HTTPNotFound()


async def handle_serve_setup(request: web.Request) -> web.StreamResponse:
    """GET /setup - Serves first-launch setup wizard page."""
    setup_file = WEBAPP_DIR / "setup.html"
    if setup_file.exists():
        return web.FileResponse(setup_file)
    return web.HTTPNotFound()


async def handle_get_setup_status(request: web.Request) -> web.Response:
    """GET /api/setup/status - Checks setup completion and standalone mode."""
    return web.json_response({
        "setup_completed": _is_setup_completed(),
        "has_telegram": bool(getattr(config, "TELEGRAM_BOT_TOKEN", "")),
        "has_admin_pass": bool(getattr(config, "WEB_ADMIN_PASSWORD", "") or getattr(config, "API_SECRET_KEY", "")),
    })


async def handle_post_setup(request: web.Request) -> web.Response:
    """
    POST /api/setup - Processes first-launch interactive setup wizard.
    Saves admin password, telegram bot token, admin chat ID, and farm settings to .env dynamically.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    admin_password = str(data.get("admin_password") or "").strip()
    bot_token = str(data.get("telegram_bot_token") or "").strip()
    admin_chat_id = str(data.get("admin_chat_id") or "").strip()
    electricity_cost = str(data.get("electricity_cost") or "4.32").strip()

    if not admin_password:
        return web.json_response({"error": "Майстер-пароль адміністратора є обов'язковим!"}, status=400)

    # Save to .env dynamically
    update_env_key("WEB_ADMIN_PASSWORD", admin_password)
    update_env_key("API_SECRET_KEY", admin_password)
    if bot_token:
        update_env_key("TELEGRAM_BOT_TOKEN", bot_token)
    if admin_chat_id:
        update_env_key("ADMIN_CHAT_ID", admin_chat_id)
    if electricity_cost:
        update_env_key("ELECTRICITY_COST_PER_KWH", electricity_cost)

    # Update in-memory config symbols
    config.WEB_ADMIN_PASSWORD = admin_password
    config.API_SECRET_KEY = admin_password
    if bot_token:
        config.TELEGRAM_BOT_TOKEN = bot_token
    if admin_chat_id:
        config.ADMIN_CHAT_ID = admin_chat_id
    try:
        config.ELECTRICITY_COST_PER_KWH = float(electricity_cost)
    except ValueError:
        pass

    # Create session token
    session_token = create_web_session()
    response = web.json_response({
        "status": "ok",
        "message": "Налаштування успішно збережено!",
        "token": session_token,
    })
    response.set_cookie("3d_farm_session", session_token, max_age=86400 * 7, httponly=True)
    return response


async def handle_post_login(request: web.Request) -> web.Response:
    """
    POST /api/auth/login - Validates Master Password or API Key and issues a session cookie/token.
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    password = str(data.get("password") or "").strip()
    expected_pass = getattr(config, "WEB_ADMIN_PASSWORD", "") or getattr(config, "API_SECRET_KEY", "")

    if not expected_pass:
        # If no password configured yet, allow setup
        return web.json_response({"error": "Система ще не налаштована. Перейдіть до /setup"}, status=400)

    if password != expected_pass:
        return web.json_response({"error": "Невірний пароль доступу!"}, status=401)

    session_token = create_web_session()
    response = web.json_response({
        "status": "ok",
        "message": "Успішний вхід у систему!",
        "token": session_token,
    })
    response.set_cookie("3d_farm_session", session_token, max_age=86400 * 7, httponly=True)
    return response


async def handle_post_logout(request: web.Request) -> web.Response:
    """POST /api/auth/logout - Revokes session token and clears cookie."""
    token = request.cookies.get("3d_farm_session") or request.headers.get("X-Session-Token")
    revoke_web_session(token)

    response = web.json_response({"status": "ok", "message": "Ви вийшли з системи"})
    response.del_cookie("3d_farm_session")
    return response


async def handle_get_session(request: web.Request) -> web.Response:
    """GET /api/auth/session - Checks current session status."""
    token = request.cookies.get("3d_farm_session") or request.headers.get("X-Session-Token")
    valid = is_valid_web_session(token)
    return web.json_response({
        "authenticated": valid,
        "setup_completed": _is_setup_completed(),
    })
