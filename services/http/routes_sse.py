"""
Server-Sent Events (SSE) telemetry streaming endpoints with Centralized Pub/Sub Broadcaster.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiohttp import web

from config import SSE_INTERVAL_SECONDS, logger
from services.http.auth import check_auth
from services.http.routes_printers import build_printer_telemetry


class SSEBroadcaster:
    """Centralized Pub/Sub broadcaster for real-time printer telemetry and keepalive comments.

    Ensures telemetry is serialized only once per tick across all connected WebApp clients,
    reducing CPU and memory churn on low-power devices like Raspberry Pi Zero 2W.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._broadcast_task: asyncio.Task[None] | None = None
        self._last_snapshot: str = "data: []\n\n"
        self._lock = asyncio.Lock()
        self._running = False

    async def subscribe(self) -> asyncio.Queue[str]:
        """Subscribes a new client and immediately delivers the latest snapshot."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
        async with self._lock:
            self._subscribers.add(queue)
            # Push latest cached snapshot immediately so client doesn't wait
            try:
                queue.put_nowait(self._last_snapshot)
            except asyncio.QueueFull:
                pass
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Unsubscribes a client queue."""
        async with self._lock:
            self._subscribers.discard(queue)

    def ensure_broadcaster(self, app_obj: Any) -> None:
        """Starts the background broadcast task if not already running."""
        if (self._broadcast_task is None or self._broadcast_task.done()) and not self._running:
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._broadcast_task = loop.create_task(self._broadcast_loop(app_obj))
            except RuntimeError:
                pass

    async def stop(self) -> None:
        """Stops the broadcaster task cleanly."""
        self._running = False
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

    async def _broadcast_loop(self, app_obj: Any) -> None:
        """Central loop serializing telemetry once per interval and dispatching to all subscribers."""
        last_ping_time = time.monotonic()
        try:
            while self._running:
                # Idle CPU optimization: Do not serialize JSON if no WebApp clients are connected
                async with self._lock:
                    has_subscribers = bool(self._subscribers)
                if not has_subscribers:
                    await asyncio.sleep(1.0)
                    continue

                # 1. Check if keepalive ping is due (every 15s to keep mobile NATs / proxies alive)
                now = time.monotonic()
                if now - last_ping_time >= 15.0:
                    last_ping_time = now
                    ping_payload = ": ping\n\n"
                    async with self._lock:
                        for q in list(self._subscribers):
                            try:
                                q.put_nowait(ping_payload)
                            except asyncio.QueueFull:
                                pass

                # 2. Serialize telemetry once for all clients
                try:
                    printers_map = getattr(app_obj, "printers", {})
                    printers_list = list(printers_map.values()) if isinstance(printers_map, dict) else []
                    printers_data = [build_printer_telemetry(p) for p in printers_list]
                    payload = f"data: {json.dumps(printers_data)}\n\n"
                    self._last_snapshot = payload
                except Exception as e:
                    logger.warning(f"Error building SSE telemetry snapshot: {e}")
                    payload = self._last_snapshot

                # 3. Fan-out to all connected subscribers
                async with self._lock:
                    for q in list(self._subscribers):
                        try:
                            q.put_nowait(payload)
                        except asyncio.QueueFull:
                            # Drop oldest if queue is full to avoid memory leaks on slow clients
                            try:
                                q.get_nowait()
                                q.put_nowait(payload)
                            except (asyncio.QueueEmpty, asyncio.QueueFull):
                                pass

                await asyncio.sleep(SSE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False


# Global singleton broadcaster instance
broadcaster = SSEBroadcaster()


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
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)
    app_obj = request.app["app_obj"]

    broadcaster.ensure_broadcaster(app_obj)
    queue = await broadcaster.subscribe()

    try:
        while True:
            if request.transport is None or request.transport.is_closing():
                break
            try:
                # Wait for next broadcast or heartbeat comment
                payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                await response.write(payload.encode("utf-8"))
            except asyncio.TimeoutError:
                # Fallback heartbeat if broadcaster was delayed
                await response.write(b": ping\n\n")
    except (asyncio.CancelledError, ConnectionError, RuntimeError):
        pass
    finally:
        await broadcaster.unsubscribe(queue)

    return response
