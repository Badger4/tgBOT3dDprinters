"""
Bambu Lab Port 6000 TLS Binary Stream Frame Grabber & HTTP camera client.
"""
import socket
import ssl
import struct
import asyncio
import urllib.request
from typing import Optional
from config import logger

async def check_tcp_port_open(ip: str, port: int, timeout: float = 1.0) -> bool:
    """Fast non-blocking check if IP:port is open."""
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

def _fetch_bambu_port6000_jpeg(ip: str, access_code: str) -> Optional[bytes]:
    """
    Connects to Bambu Lab Port 6000 TLS Stream, sends binary authentication packet,
    and returns exact JPEG frame with header length parsing.
    """
    raw_socket = None
    ssl_sock = None
    try:
        raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.settimeout(3.5)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        ssl_sock = context.wrap_socket(raw_socket)
        ssl_sock.connect((ip, 6000))

        # Build 64-byte binary authentication packet
        username = b'bblp'
        password = str(access_code or "").encode('utf-8')[:32]

        auth_packet = struct.pack('<I', 0x40)    # Payload size (64)
        auth_packet += struct.pack('<I', 0x3000)  # Packet type
        auth_packet += struct.pack('<I', 0)       # Flags
        auth_packet += struct.pack('<I', 0)       # Reserved
        auth_packet += username.ljust(32, b'\x00')
        auth_packet += password.ljust(32, b'\x00')

        ssl_sock.sendall(auth_packet)

        def recv_exact(n: int) -> bytes:
            buf = bytearray()
            while len(buf) < n:
                chunk = ssl_sock.recv(n - len(buf))
                if not chunk:
                    break
                buf.extend(chunk)
            return bytes(buf)

        # Read 16-byte header
        hdr = recv_exact(16)
        if len(hdr) < 16:
            return None

        psize, _, _, _ = struct.unpack('<IIII', hdr)
        if psize <= 0 or psize > 500000:
            return None

        # Read exact payload image bytes
        img = recv_exact(psize)

        if b'\xff\xd8' in img:
            start_idx = img.find(b'\xff\xd8')
            end_idx = img.rfind(b'\xff\xd9')
            if end_idx > start_idx:
                jpeg_bytes = img[start_idx:end_idx + 2]
                logger.info(f"✅ Captured {len(jpeg_bytes)} bytes JPEG frame from {ip}:6000")
                return jpeg_bytes

    except Exception as e:
        logger.warning(f"Port 6000 TLS stream fetch error for {ip}: {e}")
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

async def capture_real_camera_photo(ip: str, access_code: str) -> Optional[bytes]:
    """Asynchronously fetches real camera photo using Port 6000 TLS stream with retries."""
    if not ip or not access_code:
        return None

    # Try up to 2 attempts with short 0.3s delay for stability
    for attempt in range(1, 3):
        is_6000_open = await check_tcp_port_open(ip, 6000, timeout=1.0)
        if is_6000_open:
            logger.info(f"📷 Attempt {attempt}: Port 6000 open on {ip}. Fetching JPEG...")
            frame = await asyncio.to_thread(_fetch_bambu_port6000_jpeg, ip, access_code)
            if frame:
                return frame
        await asyncio.sleep(0.3)

    # HTTP Fallback
    is_80_open = await check_tcp_port_open(ip, 80, timeout=0.8)
    if is_80_open:
        import aiohttp
        http_urls = [f"http://{ip}/cam.jpg", f"https://{ip}/cam.jpg", f"http://{ip}:8080/cam.jpg"]
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=1.5)
        conn = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=conn) as session:
            for hurl in http_urls:
                try:
                    async with session.get(hurl, headers={"User-Agent": "BambuMonitor/1.0"}, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if data and len(data) > 1000:
                                return data
                except Exception:
                    pass

    return None
