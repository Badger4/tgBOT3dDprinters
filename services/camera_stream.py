"""
Bambu Lab Port 6000 TLS Binary Stream Frame Grabber & HTTP camera client.
"""

import asyncio
import socket
import ssl
import struct
import time
from typing import Any

from config import logger

# Cache of last successfully captured JPEG frame: clean_ip -> (jpeg_bytes, timestamp)
_CAMERA_FRAME_CACHE: dict[str, tuple[bytes, float]] = {}

# Circuit breaker failure tracker: clean_ip -> {"last_fail": float, "cooldown_until": float, "fail_count": int}
_CAMERA_CIRCUIT_BREAKER: dict[str, dict[str, Any]] = {}


def get_cached_camera_frame(ip: str, max_age: float = 300.0) -> bytes | None:
    """Retrieve last known good JPEG frame from cache if not expired."""
    clean_ip = str(ip or "").strip()
    if clean_ip in _CAMERA_FRAME_CACHE:
        frame, ts = _CAMERA_FRAME_CACHE[clean_ip]
        if time.time() - ts <= max_age:
            return frame
    return None


def clear_camera_cache() -> None:
    """Reset in-memory frame cache and circuit breaker state."""
    _CAMERA_FRAME_CACHE.clear()
    _CAMERA_CIRCUIT_BREAKER.clear()


async def check_tcp_port_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Fast non-blocking check if IP:port is open."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def _fetch_bambu_port6000_jpeg(ip: str, access_code: str) -> bytes | None:
    """
    Connects to Bambu Lab Port 6000 TLS Stream, sends binary authentication packet,
    and returns exact JPEG frame with header length parsing.
    """
    raw_socket = None
    ssl_sock = None
    clean_ip = str(ip or "").strip()
    clean_code = str(access_code or "").strip()
    try:
        raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.settimeout(0.8)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        ssl_sock = context.wrap_socket(raw_socket)
        ssl_sock.connect((clean_ip, 6000))

        # Build 64-byte binary authentication packet
        username = b"bblp"
        password = clean_code.encode("utf-8")[:32]

        auth_packet = struct.pack("<I", 0x40)  # Payload size (64)
        auth_packet += struct.pack("<I", 0x3000)  # Packet type
        auth_packet += struct.pack("<I", 0)  # Flags
        auth_packet += struct.pack("<I", 0)  # Reserved
        auth_packet += username.ljust(32, b"\x00")
        auth_packet += password.ljust(32, b"\x00")

        ssl_sock.sendall(auth_packet)

        def recv_exact(n: int) -> bytes:
            buf = bytearray()
            while len(buf) < n:
                chunk = ssl_sock.recv(n - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            return bytes(buf)

        # Read up to 15 stream packets until JPEG frame is received
        for _ in range(15):
            hdr = recv_exact(16)
            if len(hdr) < 16:
                break
            psize, _, _, _ = struct.unpack("<IIII", hdr)
            if psize <= 0 or psize > 2000000:
                break
            img = recv_exact(psize)
            if b"\xff\xd8" in img:
                start_idx = img.find(b"\xff\xd8")
                end_idx = img.rfind(b"\xff\xd9")
                if end_idx > start_idx:
                    jpeg_bytes = img[start_idx : end_idx + 2]
                    logger.debug(f"Captured {len(jpeg_bytes)} bytes JPEG frame from {clean_ip}:6000")
                    return jpeg_bytes

    except (socket.timeout, TimeoutError):
        logger.debug(f"Port 6000 TLS stream timeout for {clean_ip} (camera in standby/asleep)")
    except Exception as e:
        logger.warning(f"Port 6000 TLS stream fetch error for {clean_ip}: {e}")
    finally:
        if ssl_sock:
            try:
                ssl_sock.close()
            except Exception:
                pass
        elif raw_socket:
            try:
                raw_socket.close()
            except Exception:
                pass

    return None


async def capture_real_camera_photo(ip: str, access_code: str, allow_cached: bool = True) -> bytes | None:
    """
    Asynchronously fetches real camera photo using Port 6000 TLS stream with retries,
    HTTP fallback, and an intelligent circuit breaker to prevent socket exhaustion.
    """
    if not ip or not access_code:
        return None

    clean_ip = str(ip).strip()
    clean_code = str(access_code).strip()
    now = time.time()

    # 1. Circuit breaker check: if in failure cooldown, return cached frame or None immediately
    cb = _CAMERA_CIRCUIT_BREAKER.get(clean_ip)
    if cb and now < cb.get("cooldown_until", 0.0):
        if allow_cached and clean_ip in _CAMERA_FRAME_CACHE:
            cached_bytes, cached_ts = _CAMERA_FRAME_CACHE[clean_ip]
            if now - cached_ts < 300.0:
                logger.debug(f"Returning cached camera frame for {clean_ip} during failure cooldown")
                return cached_bytes
        logger.debug(f"Camera fetch for {clean_ip} skipped (circuit breaker cooldown active)")
        return None

    # 2. Try up to 2 attempts directly attempting Port 6000 TLS frame fetch
    for attempt in range(1, 3):
        logger.debug(f"📷 Attempt {attempt}: Fetching JPEG from {clean_ip}:6000...")
        frame = await asyncio.to_thread(_fetch_bambu_port6000_jpeg, clean_ip, clean_code)
        if frame:
            _CAMERA_FRAME_CACHE[clean_ip] = (frame, now)
            if clean_ip in _CAMERA_CIRCUIT_BREAKER:
                del _CAMERA_CIRCUIT_BREAKER[clean_ip]
            return frame
        if attempt == 1:
            await asyncio.sleep(0.1)

    # 3. HTTP Fallback if Port 6000 TLS stream did not return a valid frame
    is_80_open = await check_tcp_port_open(clean_ip, 80, timeout=0.8)
    if is_80_open:
        import aiohttp

        http_urls = [f"http://{clean_ip}/cam.jpg", f"https://{clean_ip}/cam.jpg", f"http://{clean_ip}:8080/cam.jpg"]
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=1.2)
        conn = aiohttp.TCPConnector(ssl=ssl_ctx)
        try:
            async with aiohttp.ClientSession(connector=conn) as session:
                for hurl in http_urls:
                    try:
                        async with session.get(hurl, headers={"User-Agent": "BambuMonitor/1.0"}, timeout=timeout) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                if data and len(data) > 1000:
                                    _CAMERA_FRAME_CACHE[clean_ip] = (data, now)
                                    if clean_ip in _CAMERA_CIRCUIT_BREAKER:
                                        del _CAMERA_CIRCUIT_BREAKER[clean_ip]
                                    return data
                    except Exception:
                        pass
        except Exception:
            pass

    # 4. If all attempts failed, activate circuit breaker cooldown
    cb_entry = _CAMERA_CIRCUIT_BREAKER.setdefault(clean_ip, {"last_fail": 0.0, "cooldown_until": 0.0, "fail_count": 0})
    cb_entry["fail_count"] += 1
    cb_entry["last_fail"] = now
    cooldown = 30.0 if cb_entry["fail_count"] <= 2 else 60.0
    cb_entry["cooldown_until"] = now + cooldown
    logger.debug(f"Camera unreachable for {clean_ip}, circuit breaker cooldown set for {cooldown:.0f}s")

    # Graceful fallback: return last cached frame if still reasonably fresh (< 5 mins)
    if allow_cached and clean_ip in _CAMERA_FRAME_CACHE:
        cached_bytes, cached_ts = _CAMERA_FRAME_CACHE[clean_ip]
        if now - cached_ts < 300.0:
            logger.debug(f"Returning cached camera frame for {clean_ip} after failed live probe")
            return cached_bytes

    return None


def stream_bambu_port6000_jpegs(ip: str, access_code: str, max_frames: int = 5000) -> Any:
    """
    Connects to Bambu Lab Port 6000 TLS Stream, sends binary auth, and continuously yields
    JPEG frames as byte objects for real-time video streaming.
    """
    raw_socket = None
    ssl_sock = None
    clean_ip = str(ip or "").strip()
    try:
        raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.settimeout(2.0)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        ssl_sock = context.wrap_socket(raw_socket)
        ssl_sock.connect((clean_ip, 6000))

        username = b"bblp"
        password = str(access_code or "").encode("utf-8")[:32]

        auth_packet = struct.pack("<I", 0x40)
        auth_packet += struct.pack("<I", 0x3000)
        auth_packet += struct.pack("<I", 0)
        auth_packet += struct.pack("<I", 0)
        auth_packet += username.ljust(32, b"\x00")
        auth_packet += password.ljust(32, b"\x00")

        ssl_sock.sendall(auth_packet)

        def recv_exact(n: int) -> bytes:
            buf = bytearray()
            while len(buf) < n:
                chunk = ssl_sock.recv(n - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            return bytes(buf)

        frames_yielded = 0
        while frames_yielded < max_frames:
            hdr = recv_exact(16)
            if len(hdr) < 16:
                break
            psize, _, _, _ = struct.unpack("<IIII", hdr)
            if psize <= 0 or psize > 2000000:
                break
            img = recv_exact(psize)
            if b"\xff\xd8" in img:
                start_idx = img.find(b"\xff\xd8")
                end_idx = img.rfind(b"\xff\xd9")
                if end_idx > start_idx:
                    jpeg_bytes = img[start_idx : end_idx + 2]
                    _CAMERA_FRAME_CACHE[clean_ip] = (jpeg_bytes, time.time())
                    yield jpeg_bytes
                    frames_yielded += 1
    except (socket.timeout, TimeoutError):
        logger.debug(f"Port 6000 stream timeout for {clean_ip}")
    except Exception as e:
        logger.warning(f"Port 6000 stream error for {clean_ip}: {e}")
    finally:
        if ssl_sock:
            try:
                ssl_sock.close()
            except Exception:
                pass
        elif raw_socket:
            try:
                raw_socket.close()
            except Exception:
                pass


async def async_stream_camera_frames(ip: str, access_code: str, request: Any = None) -> Any:
    """
    Async generator yielding live JPEG frames from Bambu Lab camera.
    Retries Port 6000 TLS stream or falls back to HTTP camera snapshots.
    Exits cleanly if client disconnects or if camera is repeatedly unreachable.
    """
    if not ip or not access_code:
        return

    consecutive_failures = 0
    max_consecutive_failures = 3

    while consecutive_failures < max_consecutive_failures:
        if request is not None and (getattr(request, "transport", None) is None or request.transport.is_closing()):
            logger.debug(f"Client disconnected from camera stream for {ip}")
            return

        is_6000_open = await check_tcp_port_open(ip, 6000, timeout=0.8)
        yielded_in_loop = False
        if is_6000_open:
            def _get_frame_gen() -> Any:
                return iter(stream_bambu_port6000_jpegs(ip, access_code, max_frames=500))

            def _fetch_next(g_obj: Any) -> Any:
                return next(g_obj, None)

            try:
                gen = await asyncio.to_thread(_get_frame_gen)
                while True:
                    if request is not None and (getattr(request, "transport", None) is None or request.transport.is_closing()):
                        return
                    frame = await asyncio.to_thread(_fetch_next, gen)
                    if not frame:
                        break
                    yield frame
                    yielded_in_loop = True
                    consecutive_failures = 0
                    await asyncio.sleep(0.04)
            except Exception as stream_err:
                logger.debug(f"Live camera stream reconnecting for {ip}: {stream_err}")

        if not yielded_in_loop:
            # Fallback single frame capture if stream drops
            frame = await capture_real_camera_photo(ip, access_code)
            if frame:
                yield frame
                consecutive_failures = 0
                await asyncio.sleep(0.5)
            else:
                consecutive_failures += 1
                await asyncio.sleep(1.0)

    logger.info(f"Camera stream unavailable for {ip} after {consecutive_failures} failures. Ending stream.")
