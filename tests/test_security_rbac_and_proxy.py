"""
Comprehensive Security Tests:
1. One-time Setup lock after initial configuration (POST /api/setup).
2. Server-side RBAC admin enforcement on administrative endpoints (/api/users, /api/users/access, /api/users/delete, /api/settings, /api/history).
3. Session Cookie Security (Secure, HttpOnly, SameSite flags, path).
4. Trusted Reverse Proxy validation for X-Forwarded-For & IP rate limiting bypass prevention.
"""

import hashlib
import hmac
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

import config
from services.http.auth import (
    create_web_session,
    delete_session_cookie,
    is_admin_request,
    is_request_secure,
    is_valid_web_session,
    set_session_cookie,
)
from services.http.middleware import get_client_ip, is_trusted_proxy
from services.http_server import create_http_app
from storage.manager import StorageManager


def _generate_telegram_init_data(user_id: int, bot_token: str, username: str = "tester") -> str:
    """Generates valid Telegram initData HMAC-SHA256 query string for testing."""
    user_json = json.dumps({"id": user_id, "first_name": "Test", "username": username}, separators=(",", ":"))
    auth_date = str(int(time.time()))
    data_dict = {
        "auth_date": auth_date,
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": user_json,
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"auth_date={auth_date}&query_id=AAHdF6IQAAAAAN0XohDhrOrc&user={user_json}&hash={hash_val}"


class DummyAppWithRBAC:
    def __init__(self, temp_dir: str):
        self.storage = StorageManager(Path(temp_dir))
        self.printers = {}
        self.global_settings = {"notify_start": True}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, uid: str) -> bool:
        if str(uid) == str(getattr(config, "ADMIN_CHAT_ID", "")):
            return True
        user = await self.storage.load_user(uid)
        return bool(user.get("is_approved", False))

    async def is_user_admin(self, uid: str) -> bool:
        if str(uid) == str(getattr(config, "ADMIN_CHAT_ID", "")):
            return True
        user = await self.storage.load_user(uid)
        return bool(user.get("role") == "ADMIN" or user.get("admin", {}).get("access_admin", False))


class TestSecurityRbacAndProxy(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bot_token = "123456789:ABCDEFghijKLMNopQRstUVwxyz"
        self.admin_id = "877001503"
        self.regular_user_id = "11223344"

        # Configure environment patches
        self.dummy_app = DummyAppWithRBAC(self.temp_dir.name)
        return create_http_app(self.dummy_app)

    async def setUpAsync(self):
        await super().setUpAsync()
        # Seed users into storage
        # 1. Main Admin
        await self.dummy_app.storage.save_user({
            "user_id": self.admin_id,
            "is_approved": True,
            "role": "ADMIN",
            "admin": {"access_admin": True},
            "personal": {"first_name": "Boss"},
        })
        # 2. Regular approved user (Operator)
        await self.dummy_app.storage.save_user({
            "user_id": self.regular_user_id,
            "is_approved": True,
            "role": "USER",
            "admin": {"access_admin": False},
            "personal": {"first_name": "Worker"},
        })
        # 3. Third user to be deleted/modified in tests
        await self.dummy_app.storage.save_user({
            "user_id": "55555555",
            "is_approved": False,
            "role": "USER",
            "admin": {"access_admin": False},
            "personal": {"first_name": "Target"},
        })

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    # ==========================================
    # 1. One-time Setup lock after first launch
    # ==========================================
    async def test_setup_locked_when_already_configured(self):
        """POST /api/setup must reject unauthenticated requests with 403 once configured."""
        with patch("config.TELEGRAM_BOT_TOKEN", self.bot_token), \
             patch("config.WEB_ADMIN_PASSWORD", "SuperPass123"), \
             patch("config.API_SECRET_KEY", "SuperPass123"):

            # Attacker tries to overwrite admin credentials
            resp = await self.client.post("/api/setup", json={
                "admin_password": "AttackerHackedPassword",
                "telegram_bot_token": "999999:Hacked",
            })
            assert resp.status == 403
            data = await resp.json()
            assert "Forbidden" in data["error"]

    async def test_setup_allowed_with_active_admin_session(self):
        """POST /api/setup succeeds when called by an authenticated admin with valid session token."""
        token = create_web_session(expiry_seconds=3600)
        with patch("config.TELEGRAM_BOT_TOKEN", self.bot_token), \
             patch("config.WEB_ADMIN_PASSWORD", "SuperPass123"), \
             patch("config.API_SECRET_KEY", "SuperPass123"), \
             patch("services.http.routes_auth.update_env_key"):

            resp = await self.client.post(
                "/api/setup",
                json={"admin_password": "NewLegitPassword123"},
                cookies={"3d_farm_session": token},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"

    # ==========================================
    # 2. Server-side RBAC Admin API Enforcement
    # ==========================================
    async def test_admin_apis_reject_regular_user_with_403(self):
        """Regular approved WebApp user (role=USER) is rejected with 403 on admin endpoints."""
        worker_init = _generate_telegram_init_data(int(self.regular_user_id), self.bot_token, "worker")
        headers = {"X-Telegram-Init-Data": worker_init}

        with patch("config.TELEGRAM_BOT_TOKEN", self.bot_token), \
             patch("config.ADMIN_CHAT_ID", self.admin_id), \
             patch("config.WEB_ADMIN_PASSWORD", "MasterPass"):

            # 1. GET /api/users
            r_get_users = await self.client.get("/api/users", headers=headers)
            assert r_get_users.status == 403
            assert "Forbidden" in (await r_get_users.json())["error"]

            # 2. POST /api/users/access
            r_access = await self.client.post("/api/users/access", json={"user_id": "55555555", "role": "ADMIN"}, headers=headers)
            assert r_access.status == 403

            # 3. POST /api/users/delete
            r_del = await self.client.post("/api/users/delete", json={"user_id": "55555555"}, headers=headers)
            assert r_del.status == 403

            # 4. DELETE /api/users/{id}
            r_del_id = await self.client.delete("/api/users/55555555", headers=headers)
            assert r_del_id.status == 403

            # 5. POST /api/settings
            r_set = await self.client.post("/api/settings", json={"notify_start": False}, headers=headers)
            assert r_set.status == 403

            # 6. DELETE /api/history
            r_hist = await self.client.delete("/api/history", headers=headers)
            assert r_hist.status == 403

    async def test_admin_apis_allow_admin_user_with_200(self):
        """Admin user (ADMIN_CHAT_ID / role=ADMIN) can access administrative endpoints."""
        admin_init = _generate_telegram_init_data(int(self.admin_id), self.bot_token, "boss")
        headers = {"X-Telegram-Init-Data": admin_init}

        with patch("config.TELEGRAM_BOT_TOKEN", self.bot_token), \
             patch("config.ADMIN_CHAT_ID", self.admin_id), \
             patch("config.WEB_ADMIN_PASSWORD", "MasterPass"):

            # 1. GET /api/users
            r_get_users = await self.client.get("/api/users", headers=headers)
            assert r_get_users.status == 200
            users = (await r_get_users.json())["users"]
            assert len(users) >= 3

            # 2. POST /api/users/access
            r_access = await self.client.post("/api/users/access", json={"user_id": "55555555", "approved": True, "role": "ADMIN"}, headers=headers)
            assert r_access.status == 200

            # 3. POST /api/settings
            r_set = await self.client.post("/api/settings", json={"notify_start": False}, headers=headers)
            assert r_set.status == 200

            # 4. POST /api/users/delete
            r_del = await self.client.post("/api/users/delete", json={"user_id": "55555555"}, headers=headers)
            assert r_del.status == 200

    # ==========================================
    # 3. Cookie Security & Flags
    # ==========================================
    def test_session_cookie_flags_http_vs_https(self):
        resp_http = web.Response()
        req_http = MagicMock(spec=web.Request)
        req_http.scheme = "http"
        req_http.headers = {}
        req_http.cookies = {}

        with patch("config.COOKIE_SECURE", ""), \
             patch("config.COOKIE_SAMESITE", "Lax"), \
             patch("config.WEBAPP_URL", "http://localhost:8080"):
            set_session_cookie(resp_http, "test_token_123", req_http)
            cookie_http = resp_http.cookies["3d_farm_session"]
            assert cookie_http["httponly"] is True
            assert cookie_http["samesite"] == "Lax"
            assert cookie_http["path"] == "/"
            assert bool(cookie_http["secure"]) is False

        # Now with HTTPS proxy or WEBAPP_URL https
        resp_https = web.Response()
        with patch("config.COOKIE_SECURE", ""), \
             patch("config.COOKIE_SAMESITE", "Lax"), \
             patch("config.WEBAPP_URL", "https://divorcee-obtrusive-secluding.ngrok-free.dev"):
            set_session_cookie(resp_https, "test_token_456", req_http)
            cookie_https = resp_https.cookies["3d_farm_session"]
            assert cookie_https["httponly"] is True
            assert bool(cookie_https["secure"]) is True
            assert cookie_https["samesite"] == "Lax"

        # Test cookie deletion
        delete_session_cookie(resp_https)
        assert resp_https.cookies["3d_farm_session"]["max-age"] == "0"
        assert resp_https.cookies["3d_farm_session"]["path"] == "/"

    # ==========================================
    # 4. Trusted Reverse Proxy & Rate Limiting
    # ==========================================
    def test_trusted_proxy_validation_logic(self):
        trusted_proxies = ["127.0.0.1", "::1", "10.0.0.0/8", "192.168.1.1"]

        assert is_trusted_proxy("127.0.0.1", trusted_proxies) is True
        assert is_trusted_proxy("::1", trusted_proxies) is True
        assert is_trusted_proxy("10.0.1.25", trusted_proxies) is True
        assert is_trusted_proxy("192.168.1.1", trusted_proxies) is True

        # Untrusted remote addresses
        assert is_trusted_proxy("192.168.1.100", trusted_proxies) is False
        assert is_trusted_proxy("8.8.8.8", trusted_proxies) is False
        assert is_trusted_proxy("172.16.0.1", trusted_proxies) is False
        assert is_trusted_proxy(None, trusted_proxies) is False
        assert is_trusted_proxy("invalid_ip", trusted_proxies) is False

    def test_get_client_ip_ignores_untrusted_forwarded_for(self):
        req_untrusted = MagicMock(spec=web.Request)
        req_untrusted.remote = "192.168.1.100"
        req_untrusted.headers = {"X-Forwarded-For": "203.0.113.195"}

        with patch("config.get_trusted_proxies", return_value=["127.0.0.1", "::1"]):
            # Request came from 192.168.1.100 (untrusted), so X-Forwarded-For MUST BE IGNORED
            detected_ip = get_client_ip(req_untrusted)
            assert detected_ip == "192.168.1.100"
            assert detected_ip != "203.0.113.195"

    def test_get_client_ip_trusts_forwarded_for_from_trusted_proxy(self):
        req_trusted = MagicMock(spec=web.Request)
        req_trusted.remote = "127.0.0.1"
        req_trusted.headers = {"X-Forwarded-For": "203.0.113.195, 127.0.0.1"}

        with patch("config.get_trusted_proxies", return_value=["127.0.0.1", "::1"]):
            # Request came from 127.0.0.1 (trusted proxy), so X-Forwarded-For client IP is TRUSTED
            detected_ip = get_client_ip(req_trusted)
            assert detected_ip == "203.0.113.195"
