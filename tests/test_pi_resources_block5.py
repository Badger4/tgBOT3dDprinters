import asyncio
import io
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

import config
from config import SensitiveDataFilter
from services.camera_stream import async_stream_camera_frames
from services.ftps_client import fetch_bambu_ftps_info
from services.http.middleware import (
    IP_AUTH_LOGS,
    MAX_AUTH_PER_MINUTE,
    security_and_ratelimit_middleware,
)


# =========================================================================
# 1. FTPS OOM Prevention & Streaming
# =========================================================================
def test_fetch_bambu_ftps_info_rejects_oversized_file():
    mock_ftps = MagicMock()
    mock_ftps.nlst.return_value = ["model_huge.3mf"]
    # 50 MB > 35 MB limit
    mock_ftps.size.return_value = 50 * 1024 * 1024

    with patch("services.ftps_client.ImplicitFTP_TLS", return_value=mock_ftps):
        res = fetch_bambu_ftps_info("192.168.1.100", "12345678", "model_huge.3mf")
        assert res == {}
        # retrbinary must NOT be called for oversized file
        mock_ftps.retrbinary.assert_not_called()


def test_fetch_bambu_ftps_info_streams_to_disk_and_cleans_up():
    mock_ftps = MagicMock()
    mock_ftps.nlst.return_value = ["model_small.3mf"]
    mock_ftps.size.return_value = 2 * 1024 * 1024

    created_temp_path = None

    def fake_retr(cmd, callback):
        callback(b"PK\x03\x04fake_zip_bytes")

    mock_ftps.retrbinary.side_effect = fake_retr

    def fake_parse(path, filename):
        nonlocal created_temp_path
        created_temp_path = Path(path)
        assert created_temp_path.exists()
        return {"valid": True, "weight_g": 42.0}

    with patch("services.ftps_client.ImplicitFTP_TLS", return_value=mock_ftps), \
         patch("services.gcode_parser.parse_3mf_file", side_effect=fake_parse):
        res = fetch_bambu_ftps_info("192.168.1.100", "12345678", "model_small.3mf")
        assert res.get("weight_g") == 42.0

        # After function returns, temporary file MUST be unlinked (cleaned up)
        assert created_temp_path is not None
        assert not created_temp_path.exists()


# =========================================================================
# 2. Camera Stream Generator Cleanup & Socket Leak Prevention
# =========================================================================
@pytest.mark.asyncio
async def test_camera_stream_closes_generator_on_client_disconnect():
    closed_called = False

    def mock_gen_fn(ip, code, max_frames=500):
        nonlocal closed_called
        try:
            while True:
                yield b"fake_jpeg_bytes"
        finally:
            closed_called = True

    mock_req = MagicMock()
    mock_req.transport = MagicMock()
    is_closing = False
    mock_req.transport.is_closing = lambda: is_closing

    with patch("services.camera_stream.check_tcp_port_open", AsyncMock(return_value=True)), \
         patch("services.camera_stream.stream_bambu_port6000_jpegs", side_effect=mock_gen_fn):
        frames = []
        async for frame in async_stream_camera_frames("192.168.1.105", "pass123", request=mock_req):
            frames.append(frame)
            # Simulate client disconnect after receiving first frame
            is_closing = True

        assert len(frames) == 1
        # Generator's finally block MUST run and close the socket
        assert closed_called is True


# =========================================================================
# 3. SensitiveDataFilter Security & Redundant Pass Removal
# =========================================================================
def test_sensitive_data_filter_masks_web_admin_password():
    flt = SensitiveDataFilter()

    with patch.object(config, "WEB_ADMIN_PASSWORD", "SuperSecretMasterPass123!"):
        record1 = logging.LogRecord("test", logging.INFO, "test.py", 1, "User login with SuperSecretMasterPass123! attempted", (), None)
        flt.filter(record1)
        assert "SuperSecretMasterPass123!" not in record1.msg
        assert "[WEB_ADMIN_PASSWORD_MASKED]" in record1.msg

        record2 = logging.LogRecord("test", logging.INFO, "test.py", 1, 'POST payload: {"password": "MySecretPass_999"}', (), None)
        flt.filter(record2)
        assert "MySecretPass_999" not in record2.msg
        assert "••••••••" in record2.msg

        record3 = logging.LogRecord("test", logging.INFO, "test.py", 1, "GET /login?password=my_query_pass&foo=bar", (), None)
        flt.filter(record3)
        assert "my_query_pass" not in record3.msg
        assert "••••••••" in record3.msg


def test_logging_configuration_attaches_filter_only_to_handlers():
    root_lg = logging.getLogger()
    # Root logger itself should NOT have duplicate sensitive filter attached
    # (it is attached to file_handler and stream_handler to prevent 4x redundant passes per line)
    root_filters = [f for f in root_lg.filters if isinstance(f, SensitiveDataFilter)]
    assert len(root_filters) == 0

    # Handlers attached to root MUST have the filter
    assert any(isinstance(f, SensitiveDataFilter) for f in config.file_handler.filters)
    assert any(isinstance(f, SensitiveDataFilter) for f in config.stream_handler.filters)


# =========================================================================
# 4. deploy_to_pi.py No Hardcoded Password
# =========================================================================
def test_deploy_to_pi_no_hardcoded_password():
    deploy_script = Path(__file__).resolve().parent.parent / "scripts" / "deploy_to_pi.py"
    text = deploy_script.read_text(encoding="utf-8")
    assert "ADM82172" not in text
    assert 'DEFAULT_PASS = os.environ.get("PI_PASS")' in text


# =========================================================================
# 5. /api/auth/login Rate Limiter Protection
# =========================================================================
@pytest.mark.asyncio
async def test_auth_login_rate_limiting():
    IP_AUTH_LOGS.clear()
    client_ip = "192.168.1.99"

    req = MagicMock(spec=web.Request)
    req.method = "POST"
    req.path = "/api/auth/login"
    req.headers = {"X-Forwarded-For": client_ip}
    req.rel_url = "/api/auth/login"
    req.remote = client_ip

    async def fake_handler(r):
        return web.Response(text="ok")

    # Send MAX_AUTH_PER_MINUTE (10) allowed requests
    for _ in range(MAX_AUTH_PER_MINUTE):
        resp = await security_and_ratelimit_middleware(req, fake_handler)
        assert resp.status == 200

    # 11th request MUST be blocked with 429 Too Many Requests
    blocked_resp = await security_and_ratelimit_middleware(req, fake_handler)
    assert blocked_resp.status == 429
    assert blocked_resp.headers.get("X-RateLimit-Limit") == "10"
