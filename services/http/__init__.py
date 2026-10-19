"""
Modular HTTP package for 3D Printer Farm REST API & WebApp.
"""

from services.http.auth import check_auth, verify_telegram_init_data
from services.http.routes_printers import build_printer_telemetry
from services.http.routes_settings import load_commercial_presets
from services.http.server import create_http_app, start_http_server

__all__ = [
    "create_http_app",
    "start_http_server",
    "check_auth",
    "verify_telegram_init_data",
    "build_printer_telemetry",
    "load_commercial_presets",
]
