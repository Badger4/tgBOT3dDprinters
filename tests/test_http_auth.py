import hashlib
import hmac
import json
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from services.http.auth import check_auth, verify_telegram_init_data

# --- verify_telegram_init_data tests ---


def create_init_data(data_dict, bot_token):
    # data_dict shouldn't contain 'hash'
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    data_dict["hash"] = calculated_hash
    return urllib.parse.urlencode(data_dict)


def test_verify_valid_signature_with_user():
    bot_token = "TEST_TOKEN"
    user_data = {"id": 123, "first_name": "Test"}
    data = {"auth_date": "1600000000", "query_id": "q123", "user": json.dumps(user_data)}
    init_data = create_init_data(data, bot_token)

    result = verify_telegram_init_data(init_data, bot_token)
    assert result == user_data


def test_verify_invalid_hash():
    bot_token = "TEST_TOKEN"
    data = {"auth_date": "1600000000", "query_id": "q123", "user": '{"id":1}'}
    init_data = create_init_data(data, bot_token)
    init_data = init_data.replace("hash=", "hash=wrong")

    result = verify_telegram_init_data(init_data, bot_token)
    assert result is None


def test_verify_empty_inputs():
    assert verify_telegram_init_data("", "token") is None
    assert verify_telegram_init_data("some_data", "") is None


def test_verify_no_hash():
    result = verify_telegram_init_data("auth_date=123", "token")
    assert result is None


def test_verify_valid_no_user():
    bot_token = "TEST_TOKEN"
    data = {"auth_date": "1600000000", "query_id": "q123"}
    init_data = create_init_data(data, bot_token)

    result = verify_telegram_init_data(init_data, bot_token)
    assert result == {"valid": True}


def test_verify_malformed_user():
    bot_token = "TEST_TOKEN"
    data = {"auth_date": "1600000000", "user": "{malformed_json:"}
    init_data = create_init_data(data, bot_token)

    result = verify_telegram_init_data(init_data, bot_token)
    assert result is None


# --- check_auth tests ---


@pytest.fixture
def mock_app():
    app = web.Application()
    app_obj = MagicMock()

    async def is_user_approved(u_id):
        return u_id == "123"

    app_obj.is_user_approved = is_user_approved
    app["app_obj"] = app_obj
    return app


@pytest.mark.asyncio
async def test_check_auth_valid_api_key_header(mock_app):
    with patch("services.http.auth.API_SECRET_KEY", "secret123"):
        req = make_mocked_request("GET", "/", headers={"X-API-Key": "secret123"}, app=mock_app)
        assert await check_auth(req) is True


@pytest.mark.asyncio
async def test_check_auth_valid_api_key_query(mock_app):
    with patch("services.http.auth.API_SECRET_KEY", "secret123"):
        req = make_mocked_request("GET", "/?token=secret123", app=mock_app)
        assert await check_auth(req) is True


@pytest.mark.asyncio
async def test_check_auth_valid_init_data_approved(mock_app):
    bot_token = "TEST_TOKEN"
    user_data = {"id": 123}
    data = {"auth_date": "1600000000", "user": json.dumps(user_data)}
    init_data = create_init_data(data, bot_token)

    with patch("services.http.auth.TELEGRAM_BOT_TOKEN", bot_token):
        req = make_mocked_request("GET", f"/?initData={urllib.parse.quote(init_data)}", app=mock_app)
        assert await check_auth(req) is True


@pytest.mark.asyncio
async def test_check_auth_valid_init_data_unapproved(mock_app):
    bot_token = "TEST_TOKEN"
    user_data = {"id": 999}  # not approved
    data = {"auth_date": "1600000000", "user": json.dumps(user_data)}
    init_data = create_init_data(data, bot_token)

    with patch("services.http.auth.TELEGRAM_BOT_TOKEN", bot_token):
        req = make_mocked_request("GET", f"/?initData={urllib.parse.quote(init_data)}", app=mock_app)
        assert await check_auth(req) is False


@pytest.mark.asyncio
async def test_check_auth_invalid_init_data(mock_app):
    with patch("services.http.auth.TELEGRAM_BOT_TOKEN", "token"):
        req = make_mocked_request("GET", "/?initData=invalid", app=mock_app)
        assert await check_auth(req) is False


@pytest.mark.asyncio
async def test_check_auth_localhost_fallback(mock_app):
    with patch("services.http.auth.API_SECRET_KEY", None):
        # make_mocked_request remote is usually 127.0.0.1 by default
        req = make_mocked_request("GET", "/", app=mock_app)
        assert await check_auth(req) is True


@pytest.mark.asyncio
async def test_check_auth_external_request(mock_app):
    with patch("services.http.auth.API_SECRET_KEY", None):
        # Adding X-Forwarded-For makes it a tunnel request, should be False
        req = make_mocked_request("GET", "/", headers={"X-Forwarded-For": "1.2.3.4"}, app=mock_app)
        assert await check_auth(req) is False


@pytest.mark.asyncio
async def test_check_auth_no_credentials_tunnel(mock_app):
    with patch("services.http.auth.API_SECRET_KEY", "secret"):
        req = make_mocked_request("GET", "/", headers={"X-Forwarded-For": "1.2.3.4"}, app=mock_app)
        assert await check_auth(req) is False
