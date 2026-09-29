import ipaddress
import time
from typing import Any

from aiohttp import web

import config
from config import HTTP_PORT, WEBAPP_URL, get_trusted_proxies, logger


def is_trusted_proxy(remote_ip: str | None, trusted_list: list[str]) -> bool:
    """Checks whether remote_ip matches any trusted proxy IP or CIDR network."""
    if not remote_ip:
        return False
    try:
        remote_addr = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False

    for item in trusted_list:
        item = item.strip()
        if not item:
            continue
        try:
            if "/" in item:
                if remote_addr in ipaddress.ip_network(item, strict=False):
                    return True
            else:
                if remote_addr == ipaddress.ip_address(item):
                    return True
        except ValueError:
            continue
    return False


def get_client_ip(request: web.Request) -> str:
    """
    Safely extracts client IP address.
    X-Forwarded-For is only trusted when the direct connection originates
    from a verified trusted reverse proxy (e.g. 127.0.0.1, ::1, or TRUSTED_PROXIES).
    """
    remote = request.remote or "127.0.0.1"
    trusted = get_trusted_proxies()
    if is_trusted_proxy(remote, trusted):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return remote

# IP Rate Limiting storage: ip -> list of request timestamps
IP_REQUEST_LOGS: dict[str, list[float]] = {}
IP_UPLOAD_LOGS: dict[str, list[float]] = {}
IP_CONTROL_LOGS: dict[str, list[float]] = {}

MAX_REQ_PER_MINUTE = 300
MAX_UPLOADS_PER_MINUTE = 30
MAX_CONTROL_PER_MINUTE = 20


_WEBAPP_CLEAN = WEBAPP_URL.rstrip("/") if WEBAPP_URL else ""
ALLOWED_ORIGINS = {
    _WEBAPP_CLEAN,
    "https://web.telegram.org",
    f"http://localhost:{HTTP_PORT}",
    f"http://127.0.0.1:{HTTP_PORT}",
}
ALLOWED_ORIGINS.discard("")

STATIC_SECURITY_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, DELETE, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data, X-API-Key, Bypass-Tunnel-Reminder, Authorization",
    "Access-Control-Max-Age": "86400",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self' https: data: blob:; "
        "script-src 'self' https://telegram.org https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https: wss: ws:; "
        "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;"
    ),
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def _apply_cors_and_security_headers(request: web.Request, response: web.StreamResponse) -> None:
    origin = request.headers.get("Origin", "")
    if origin and origin.rstrip("/") in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "null"

    response.headers.update(STATIC_SECURITY_HEADERS)

    # Smart Caching: Static assets (versioned) are cached; dynamic API/HTML/app.js/style.css are fresh
    path = request.path
    if (path.startswith("/static/") or path.startswith("/uploads/")) and not path.endswith("app.js") and not path.endswith("style.css"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    else:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"


@web.middleware
async def security_and_ratelimit_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
    # 1. Handle CORS Preflight OPTIONS requests
    if request.method == "OPTIONS":
        response = web.Response(status=204)
        _apply_cors_and_security_headers(request, response)
        return response

    # 2. Redirect insecure external proxy requests to HTTPS when configured
    proto = request.headers.get("X-Forwarded-Proto", "").lower()
    if proto == "http" and getattr(config, "WEBAPP_URL", "").lower().startswith("https://"):
        host = request.headers.get("X-Forwarded-Host") or request.host
        return web.HTTPMovedPermanently(f"https://{host}{request.rel_url}")

    client_ip = get_client_ip(request)
    now = time.time()

    is_upload = request.path == "/api/files/upload"
    is_control = "/control" in request.path or "/commercial/presets" in request.path or "/access_code" in request.path

    if is_upload:
        target_logs = IP_UPLOAD_LOGS
        limit = MAX_UPLOADS_PER_MINUTE
    elif is_control:
        target_logs = IP_CONTROL_LOGS
        limit = MAX_CONTROL_PER_MINUTE
    else:
        target_logs = IP_REQUEST_LOGS
        limit = MAX_REQ_PER_MINUTE

    # Clean up old timestamps (> 60s) for current IP
    timestamps = [t for t in target_logs.get(client_ip, []) if now - t < 60.0]

    # Periodic garbage collection if IP log dictionary exceeds 1000 entries
    if len(target_logs) > 1000:
        for ip_key in list(target_logs.keys()):
            valid_ts = [t for t in target_logs[ip_key] if now - t < 60.0]
            if valid_ts:
                target_logs[ip_key] = valid_ts
            else:
                target_logs.pop(ip_key, None)

    remaining = max(0, limit - len(timestamps))

    if len(timestamps) >= limit:
        logger.warning(f"⛔ Rate limit exceeded for IP [{client_ip}] on {request.path}")
        response = web.json_response(
            {"error": "Too Many Requests", "message": "Rate limit exceeded. Please wait 60 seconds."}, status=429
        )
        _apply_cors_and_security_headers(request, response)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        response.headers["X-RateLimit-Reset"] = "60"
        return response

    timestamps.append(now)
    target_logs[client_ip] = timestamps

    # Process request
    response = await handler(request)

    # Apply HTTP Security, CORS & Rate Limit Headers
    _apply_cors_and_security_headers(request, response)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, remaining - 1))

    if not response.prepared:
        try:
            response.enable_compression()
        except Exception:
            pass

    return response
