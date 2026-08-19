import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.camera_stream import _fetch_bambu_port6000_jpeg, capture_real_camera_photo, check_tcp_port_open


@pytest.mark.asyncio
async def test_check_tcp_port_open_success():
    writer = MagicMock()
    writer.wait_closed = AsyncMock()

    with patch("asyncio.open_connection", new_callable=AsyncMock) as mock_open:
        mock_open.return_value = (MagicMock(), writer)
        result = await check_tcp_port_open("1.2.3.4", 6000)
        assert result is True
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_tcp_port_open_connection_refused():
    with patch("asyncio.open_connection", side_effect=ConnectionRefusedError):
        result = await check_tcp_port_open("1.2.3.4", 6000)
        assert result is False


@pytest.mark.asyncio
async def test_check_tcp_port_open_timeout():
    with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
        result = await check_tcp_port_open("1.2.3.4", 6000)
        assert result is False


@pytest.mark.asyncio
async def test_check_tcp_port_open_general_exception():
    with patch("asyncio.open_connection", side_effect=Exception("Test")):
        result = await check_tcp_port_open("1.2.3.4", 6000)
        assert result is False


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_success(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    jpeg_data = b"junk\xff\xd8hello\xff\xd9more"
    header = struct.pack("<IIII", len(jpeg_data), 0, 0, 0)

    mock_ssl_sock.recv.side_effect = [header[:8], header[8:], jpeg_data[:4], jpeg_data[4:]]

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result == b"\xff\xd8hello\xff\xd9"
    mock_ssl_sock.close.assert_called_once()


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_connection_error(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    mock_ssl_sock.connect.side_effect = Exception("Conn error")

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result is None
    mock_ssl_sock.close.assert_called_once()


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_empty_header(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    mock_ssl_sock.recv.return_value = b""

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result is None
    mock_ssl_sock.close.assert_called_once()


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_oversized(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    header = struct.pack("<IIII", 2000001, 0, 0, 0)
    mock_ssl_sock.recv.side_effect = [header]

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result is None
    mock_ssl_sock.close.assert_called_once()


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_no_markers(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    jpeg_data = b"junkdata"
    header = struct.pack("<IIII", len(jpeg_data), 0, 0, 0)

    side_effects = []
    for _ in range(5):
        side_effects.extend([header, jpeg_data])
    mock_ssl_sock.recv.side_effect = side_effects

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result is None
    mock_ssl_sock.close.assert_called_once()


@patch("services.camera_stream.socket.socket")
@patch("services.camera_stream.ssl.create_default_context")
def test_fetch_bambu_port6000_jpeg_ssl_close_error(mock_ssl_context, mock_socket):
    mock_ssl_sock = MagicMock()
    mock_context_instance = MagicMock()
    mock_context_instance.wrap_socket.return_value = mock_ssl_sock
    mock_ssl_context.return_value = mock_context_instance

    mock_ssl_sock.recv.return_value = b""
    mock_ssl_sock.close.side_effect = Exception("Close error")

    result = _fetch_bambu_port6000_jpeg("1.2.3.4", "code")
    assert result is None


@pytest.mark.asyncio
async def test_capture_real_camera_photo_empty_ip():
    assert await capture_real_camera_photo("", "code") is None


@pytest.mark.asyncio
async def test_capture_real_camera_photo_empty_code():
    assert await capture_real_camera_photo("1.2.3.4", "") is None


@pytest.mark.asyncio
@patch("services.camera_stream.check_tcp_port_open", new_callable=AsyncMock)
@patch("services.camera_stream._fetch_bambu_port6000_jpeg")
async def test_capture_real_camera_photo_port6000_success_first(mock_fetch, mock_check):
    mock_check.return_value = True
    mock_fetch.return_value = b"jpeg"

    result = await capture_real_camera_photo("1.2.3.4", "code")
    assert result == b"jpeg"
    mock_check.assert_awaited_once_with("1.2.3.4", 6000, timeout=1.0)
    mock_fetch.assert_called_once_with("1.2.3.4", "code")


@pytest.mark.asyncio
@patch("services.camera_stream.check_tcp_port_open", new_callable=AsyncMock)
@patch("services.camera_stream._fetch_bambu_port6000_jpeg")
async def test_capture_real_camera_photo_port6000_success_retry(mock_fetch, mock_check):
    mock_check.side_effect = [False, True]
    mock_fetch.return_value = b"jpeg"

    result = await capture_real_camera_photo("1.2.3.4", "code")
    assert result == b"jpeg"
    assert mock_check.call_count == 2
    mock_fetch.assert_called_once_with("1.2.3.4", "code")


@pytest.mark.asyncio
@patch("services.camera_stream.check_tcp_port_open", new_callable=AsyncMock)
@patch("services.camera_stream._fetch_bambu_port6000_jpeg")
async def test_capture_real_camera_photo_all_fail(mock_fetch, mock_check):
    mock_check.return_value = False
    mock_fetch.return_value = b"jpeg"

    result = await capture_real_camera_photo("1.2.3.4", "code")
    assert result is None
    assert mock_check.call_count == 3


@pytest.mark.asyncio
async def test_capture_real_camera_photo_http_fallback():
    """Test that HTTP fallback path is entered when port 6000 fails but port 80 is open.
    Since aiohttp is imported inside the function body, we mock at a higher level."""
    call_log = []

    async def mock_port_check(ip, port, timeout=1.0):
        call_log.append(port)
        if port == 6000:
            return False
        if port == 80:
            return True
        return False

    with (
        patch("services.camera_stream.check_tcp_port_open", side_effect=mock_port_check),
        patch("services.camera_stream._fetch_bambu_port6000_jpeg", return_value=None),
    ):
        # Import and patch aiohttp at the right level
        import aiohttp as _aiohttp

        fake_jpeg = b"\xff\xd8" + b"\x00" * 1100 + b"\xff\xd9"

        class FakeResponseContext:
            async def __aenter__(self):
                resp = AsyncMock()
                resp.status = 200
                resp.read = AsyncMock(return_value=fake_jpeg)
                return resp

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def fake_get(self_session, url, **kwargs):
            return FakeResponseContext()

        with patch.object(_aiohttp.ClientSession, "get", fake_get):
            result = await capture_real_camera_photo("1.2.3.4", "code")
            # Verify port 80 was checked (HTTP fallback path entered)
            assert 80 in call_log
            assert result == fake_jpeg


@pytest.mark.asyncio
async def test_async_stream_camera_frames():
    from services.camera_stream import async_stream_camera_frames

    fake_frame = b"\xff\xd8" + b"\x00" * 100 + b"\xff\xd9"
    with patch("services.camera_stream.check_tcp_port_open", AsyncMock(return_value=True)):
        with patch("services.camera_stream.stream_bambu_port6000_jpegs", return_value=iter([fake_frame])):
            frames = []
            async for frame in async_stream_camera_frames("1.2.3.4", "code"):
                frames.append(frame)
                if len(frames) >= 1:
                    break
            assert len(frames) == 1
            assert frames[0] == fake_frame
