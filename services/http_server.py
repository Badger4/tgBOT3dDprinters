"""
Lightweight REST API & WebApp HTTP server for 3D Printer Farm.
Facade module that delegates routing, auth, and middlewares to submodules in services.http.
"""

from typing import Any

from aiohttp import web

from config import HTTP_PORT, logger
from services.http.auth import check_auth, verify_telegram_init_data
from services.http.middleware import security_and_ratelimit_middleware
from services.http.routes_control import handle_printer_control
from services.http.routes_files import handle_file_upload, handle_image_upload, handle_start_print_job
from services.http.routes_printers import (
    build_printer_telemetry,
    handle_create_printer,
    handle_delete_printer,
    handle_get_camera_stream,
    handle_get_printer_by_id,
    handle_get_printers,
    handle_get_snapshot,
    handle_update_access_code,
)
from services.http.routes_settings import (
    WEBAPP_DIR,
    handle_calculate_commercial,
    handle_delete_history,
    handle_delete_preset,
    handle_delete_user,
    handle_export_history_csv,
    handle_get_history,
    handle_get_presets,
    handle_get_settings,
    handle_get_user_settings,
    handle_get_users,
    handle_health,
    handle_save_preset,
    handle_serve_index,
    handle_update_settings,
    handle_update_user_access,
    handle_update_user_settings,
    load_commercial_presets,
)
from services.http.routes_parts import handle_delete_part, handle_get_parts, handle_print_part, handle_save_part
from services.http.routes_spools import (
    handle_delete_spool,
    handle_export_warehouse_csv,
    handle_get_spools,
    handle_save_spool,
)
from services.http.routes_sse import handle_sse_stream

__all__ = [
    "verify_telegram_init_data",
    "check_auth",
    "build_printer_telemetry",
    "load_commercial_presets",
    "create_http_app",
    "start_http_server",
]


def create_http_app(app_obj: Any) -> web.Application:
    """Creates aiohttp web Application with configured API routes, security middlewares & static WebApp assets."""
    web_app = web.Application(
        client_max_size=50 * 1024 * 1024,
        middlewares=[security_and_ratelimit_middleware],
    )
    web_app["app_obj"] = app_obj

    # WebApp Index & Assets
    web_app.router.add_get("/", handle_serve_index)
    web_app.router.add_get("/webapp", handle_serve_index)

    static_dir = WEBAPP_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    web_app.router.add_static("/static/", path=str(static_dir), name="static")

    import config
    uploads_dir = config.STORAGE_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    web_app.router.add_static("/uploads/", path=str(uploads_dir), name="uploads")

    # API Endpoints
    web_app.router.add_get("/health", handle_health)
    web_app.router.add_get("/api/printers", handle_get_printers)
    web_app.router.add_post("/api/printers", handle_create_printer)
    web_app.router.add_delete("/api/printers/{id}", handle_delete_printer)
    web_app.router.add_get("/api/printers/{id}", handle_get_printer_by_id)
    web_app.router.add_get("/api/printers/{id}/snapshot", handle_get_snapshot)
    web_app.router.add_get("/api/printers/{id}/stream", handle_get_camera_stream)
    web_app.router.add_post("/api/printers/{id}/control", handle_printer_control)
    web_app.router.add_post("/api/printers/{id}/access_code", handle_update_access_code)

    # File Upload & Print Job API
    web_app.router.add_post("/api/files/upload", handle_file_upload)
    web_app.router.add_post("/api/files/upload_image", handle_image_upload)
    web_app.router.add_post("/api/printers/{id}/print_file", handle_start_print_job)

    # Spools API & Warehouse Export
    web_app.router.add_get("/api/spools", handle_get_spools)
    web_app.router.add_post("/api/spools", handle_save_spool)
    web_app.router.add_delete("/api/spools/{id}", handle_delete_spool)
    web_app.router.add_get("/api/warehouse/export_csv", handle_export_warehouse_csv)

    # Parts Warehouse API
    web_app.router.add_get("/api/parts", handle_get_parts)
    web_app.router.add_post("/api/parts", handle_save_part)
    web_app.router.add_delete("/api/parts/{id}", handle_delete_part)
    web_app.router.add_post("/api/parts/{part_id}/print/{printer_id}", handle_print_part)

    # Commercial Pricing API
    web_app.router.add_get("/api/commercial/presets", handle_get_presets)
    web_app.router.add_post("/api/commercial/presets", handle_save_preset)
    web_app.router.add_delete("/api/commercial/presets/{id}", handle_delete_preset)
    web_app.router.add_post("/api/commercial/calculate", handle_calculate_commercial)

    # History & Events API
    web_app.router.add_get("/api/events", handle_sse_stream)
    web_app.router.add_get("/api/history", handle_get_history)
    web_app.router.add_delete("/api/history", handle_delete_history)
    web_app.router.add_get("/api/history/export", handle_export_history_csv)
    web_app.router.add_get("/api/settings", handle_get_settings)
    web_app.router.add_post("/api/settings", handle_update_settings)
    web_app.router.add_get("/api/user/settings", handle_get_user_settings)
    web_app.router.add_post("/api/user/settings", handle_update_user_settings)
    web_app.router.add_get("/api/users", handle_get_users)
    web_app.router.add_post("/api/users/access", handle_update_user_access)
    web_app.router.add_post("/api/users/delete", handle_delete_user)
    web_app.router.add_delete("/api/users/{id}", handle_delete_user)

    return web_app


async def start_http_server(app_obj: Any, host: str = "0.0.0.0", port: int = HTTP_PORT) -> None:
    """Starts async HTTP REST API server on specified port."""
    web_app = create_http_app(app_obj)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"🌐 [WebApp & REST API] Server started at http://{host}:{port} (WebApp: http://{host}:{port}/webapp)")
