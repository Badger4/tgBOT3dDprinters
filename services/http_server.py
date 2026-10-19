"""
Backwards-compatibility facade for services.http.server.
All HTTP REST API and WebApp server logic is maintained inside the `services.http` package.
"""

from services.http.auth import check_auth, verify_telegram_init_data
from services.http.routes_printers import build_printer_telemetry
from services.http.routes_settings import load_commercial_presets
from services.http.server import create_http_app, start_http_server

__all__ = [
    "verify_telegram_init_data",
    "check_auth",
    "build_printer_telemetry",
    "load_commercial_presets",
    "create_http_app",
    "start_http_server",
]
