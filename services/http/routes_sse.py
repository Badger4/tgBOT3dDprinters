"""
Server-Sent Events (SSE) telemetry streaming endpoints.
"""

import asyncio
import json

from aiohttp import web

from config import SSE_INTERVAL_SECONDS
from services.http.auth import check_auth
from services.http.routes_printers import build_printer_telemetry


async def handle_sse_stream(request: web.Request) -> web.StreamResponse:
    """GET /api/events - Server-Sent Events stream for real-time WebApp updates."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await response.prepare(request)
    app_obj = request.app["app_obj"]

    try:
        while True:
            printers_data = [build_printer_telemetry(p) for p in app_obj.printers.values()]
            payload = f"data: {json.dumps(printers_data)}\n\n"
            await response.write(payload.encode("utf-8"))
            await asyncio.sleep(SSE_INTERVAL_SECONDS)
    except (asyncio.CancelledError, ConnectionResetError):
        pass

    return response
