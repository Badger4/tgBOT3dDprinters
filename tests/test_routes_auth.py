"""
Unit tests for Standalone Web Login, Session Management, and First-Launch Setup Wizard.
"""

import json
import pytest
from aiohttp import web
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import config
from services.http.auth import (
    create_web_session,
    is_valid_web_session,
    revoke_web_session,
)
from services.http.routes_auth import (
    handle_get_session,
    handle_get_setup_status,
    handle_post_login,
    handle_post_logout,
    handle_post_setup,
    handle_serve_login,
    handle_serve_setup,
)


class TestRoutesAuth:
    def test_session_token_lifecycle(self):
        token = create_web_session(expiry_seconds=10)
        assert is_valid_web_session(token) is True
        revoke_web_session(token)
        assert is_valid_web_session(token) is False

    @pytest.mark.asyncio
    async def test_get_setup_status(self):
        req = MagicMock(spec=web.Request)
        res = await handle_get_setup_status(req)
        assert res.status == 200

    @pytest.mark.asyncio
    async def test_post_setup_and_login_flow(self):
        temp_dir = TemporaryDirectory()
        env_file = Path(temp_dir.name) / ".env"
        env_file.write_text("", encoding="utf-8")

        with patch("config.ENV_PATH", env_file), \
             patch("config.TELEGRAM_BOT_TOKEN", ""), \
             patch("config.WEB_ADMIN_PASSWORD", ""), \
             patch("config.API_SECRET_KEY", ""):
            setup_req = MagicMock(spec=web.Request)
            setup_req.cookies = {}
            setup_req.headers = {}
            setup_req.query = {}
            async def mock_setup_json():
                return {"admin_password": "MasterPass123!", "telegram_bot_token": "", "admin_chat_id": ""}
            setup_req.json = mock_setup_json
            res_setup = await handle_post_setup(setup_req)
            assert res_setup.status == 200

            # Test login with wrong password
            login_bad = MagicMock(spec=web.Request)
            login_bad.cookies = {}
            login_bad.headers = {}
            login_bad.query = {}
            async def mock_bad_json():
                return {"password": "WrongPassword"}
            login_bad.json = mock_bad_json
            res_login_bad = await handle_post_login(login_bad)
            assert res_login_bad.status == 401

            # Test login with correct password
            login_good = MagicMock(spec=web.Request)
            login_good.cookies = {}
            login_good.headers = {}
            login_good.query = {}
            async def mock_good_json():
                return {"password": "MasterPass123!"}
            login_good.json = mock_good_json
            res_login_good = await handle_post_login(login_good)
            assert res_login_good.status == 200

        temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_post_setup_locked_when_completed(self):
        """Verifies that once setup is completed, POST /api/setup rejects unauthenticated calls with 403."""
        with patch("config.TELEGRAM_BOT_TOKEN", "123456789:ABCDEF"), \
             patch("config.WEB_ADMIN_PASSWORD", "Secret123"), \
             patch("config.API_SECRET_KEY", "Secret123"):

            # 1. Unauthenticated request without admin session
            unauth_req = MagicMock(spec=web.Request)
            unauth_req.cookies = {}
            unauth_req.headers = {}
            unauth_req.query = {}
            unauth_req.remote = "1.2.3.4"
            async def mock_json():
                return {"admin_password": "HackedPassword!"}
            unauth_req.json = mock_json

            res_unauth = await handle_post_setup(unauth_req)
            assert res_unauth.status == 403
            err_data = json.loads(res_unauth.text)
            assert "Forbidden" in err_data.get("error", "")

            # 2. Authenticated admin request with active web session
            token = create_web_session(expiry_seconds=300)
            admin_req = MagicMock(spec=web.Request)
            admin_req.cookies = {"3d_farm_session": token}
            admin_req.headers = {}
            admin_req.query = {}
            admin_req.remote = "1.2.3.4"
            async def mock_admin_json():
                return {"admin_password": "NewAdminPassword123!"}
            admin_req.json = mock_admin_json

            temp_dir = TemporaryDirectory()
            env_file = Path(temp_dir.name) / ".env"
            env_file.write_text("", encoding="utf-8")
            with patch("config.ENV_PATH", env_file):
                res_admin = await handle_post_setup(admin_req)
                assert res_admin.status == 200
            temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_serve_login_and_setup_pages(self):
        req = MagicMock(spec=web.Request)
        res_login = await handle_serve_login(req)
        assert res_login.status == 200
        res_setup = await handle_serve_setup(req)
        assert res_setup.status == 200

    @pytest.mark.asyncio
    async def test_logout_and_session_check(self):
        token = create_web_session(expiry_seconds=600)
        req = MagicMock(spec=web.Request)
        req.cookies = {"3d_farm_session": token}
        req.headers = {}
        req.query = {}

        res_sess = await handle_get_session(req)
        assert res_sess.status == 200

        res_logout = await handle_post_logout(req)
        assert res_logout.status == 200
        assert is_valid_web_session(token) is False

    @pytest.mark.asyncio
    async def test_invalid_json_handling(self):
        with patch("config.TELEGRAM_BOT_TOKEN", ""), \
             patch("config.WEB_ADMIN_PASSWORD", ""), \
             patch("config.API_SECRET_KEY", ""):
            req_bad = MagicMock(spec=web.Request)
            req_bad.cookies = {}
            req_bad.headers = {}
            req_bad.query = {}
            async def mock_raise():
                raise ValueError("Invalid JSON")
            req_bad.json = mock_raise

            res_setup = await handle_post_setup(req_bad)
            assert res_setup.status == 400

            res_login = await handle_post_login(req_bad)
            assert res_login.status == 400

    @pytest.mark.asyncio
    async def test_setup_validation_errors(self):
        with patch("config.TELEGRAM_BOT_TOKEN", ""), \
             patch("config.WEB_ADMIN_PASSWORD", ""), \
             patch("config.API_SECRET_KEY", ""):
            req_empty = MagicMock(spec=web.Request)
            req_empty.cookies = {}
            req_empty.headers = {}
            req_empty.query = {}
            async def mock_empty_json():
                return {"admin_password": ""}
            req_empty.json = mock_empty_json
            res_setup = await handle_post_setup(req_empty)
            assert res_setup.status == 400
