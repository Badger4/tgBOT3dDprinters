"""
Unit tests for:
1. AMS Humidity Watchdog & Telemetry (ams_humidity_idx, alerts, and badges)
2. Custom Electricity Tariffs & Wattage in Commercial Calculator & PDF Export
3. Visual Spool Contrast Enhancement logic
"""

import asyncio
import html
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from models.commercial import calculate_commercial_price
from models.printer import BambuPrinter
from services.http.routes_printers import build_printer_telemetry
from services.http_server import create_http_app
from storage.manager import StorageManager


class DummyApp:
    def __init__(self, temp_dir: str):
        self.storage = StorageManager(Path(temp_dir))
        self.printers: dict[str, Any] = {}
        self.live_status_messages: dict[str, dict[str, Any]] = {}
        self.bot = AsyncMock()
        self.global_settings = {}

    async def is_user_approved(self, chat_id: str) -> bool:
        return True


# ==============================================================================
# 1. AMS HUMIDITY TELEMETRY & ALERT TESTS
# ==============================================================================


def test_build_printer_telemetry_includes_humidity():
    """Verify that build_printer_telemetry includes ams_humidity_idx, raw, and temp."""
    storage = MagicMock()
    config = {
        "id": "p-hum-1",
        "name": "P1S AMS",
        "ip": "192.168.1.50",
        "access_code": "11112222",
        "serial_number": "01P001",
        "has_ams": True,
        "ams_humidity_idx": 4,
        "ams_humidity_raw": 85,
        "ams_temp": 24.5,
    }
    printer = BambuPrinter(config, storage)
    printer.ams_humidity_idx = 4
    printer.ams_humidity_raw = 85
    printer.ams_temp = 24.5

    telemetry = build_printer_telemetry(printer)
    assert telemetry["ams_humidity_idx"] == 4
    assert telemetry["ams_humidity_raw"] == 85
    assert telemetry["ams_temp"] == 24.5
    assert telemetry["has_ams"] is True


def test_ams_humidity_alert_logic():
    """Verify the logic used in app.py Section 7 for AMS humidity alert trigger and cooldown."""
    p = MagicMock()
    p.has_ams = True
    p.notify = True
    p.name = "Bambu P1S"
    p.ams_humidity_idx = 4

    st = {"lastAmsHumidityAlert": 0.0}
    now_ts = 100000.0

    # 1. First time alert when humidity >= 4
    should_alert = False
    if getattr(p, "has_ams", False) and getattr(p, "notify", True):
        h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
        if h_idx >= 4:
            last_alert = float(st.get("lastAmsHumidityAlert", 0.0) or 0.0)
            if (now_ts - last_alert) > 43200.0:
                should_alert = True
                st["lastAmsHumidityAlert"] = now_ts

    assert should_alert is True
    assert st["lastAmsHumidityAlert"] == now_ts

    # 2. Within cooldown (e.g. 1 hour later) - should NOT alert
    now_ts += 3600.0
    should_alert_again = False
    if getattr(p, "has_ams", False) and getattr(p, "notify", True):
        h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
        if h_idx >= 4:
            last_alert = float(st.get("lastAmsHumidityAlert", 0.0) or 0.0)
            if (now_ts - last_alert) > 43200.0:
                should_alert_again = True

    assert should_alert_again is False

    # 3. Drops back to dry (<= 2) - cooldown resets
    p.ams_humidity_idx = 1
    h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
    if h_idx <= 2:
        st["lastAmsHumidityAlert"] = 0.0

    assert st["lastAmsHumidityAlert"] == 0.0


# ==============================================================================
# 2. CUSTOM ELECTRICITY CALCULATION TESTS
# ==============================================================================


def test_calculate_commercial_custom_electricity():
    """Verify that calculate_commercial_price uses custom electricity_rate_uah and power_watts."""
    preset = {
        "name": "Custom PLA",
        "price_per_g": 0.80,
        "electricity_rate_uah": 5.50,  # custom rate
        "power_watts": 200.0,  # custom power
        "depreciation_val": "0",
        "consumables_val": "0",
        "profit_val": "0%",
    }
    # 100g, 120 mins = 2.0 hours
    # kwh = (200 / 1000) * 2.0 = 0.4 kwh
    # electricity_cost = 0.4 * 5.50 = 2.20 UAH
    # filament_cost = 100 * 0.80 = 80.0 UAH
    # total = 82.20 UAH
    calc = calculate_commercial_price(preset, weight_g=100.0, time_mins=120)
    assert calc["filament_cost"] == 80.0
    assert calc["electricity_rate_uah"] == 5.50
    assert calc["power_watts"] == 200.0
    assert calc["electricity_cost"] == 2.20
    assert calc["direct_cost"] == 82.20
    assert calc["total_price"] == 82.20


# ==============================================================================
# 3. HTTP ENDPOINTS INTEGRATION TEST
# ==============================================================================


class TestHumidityAndElectricityEndpoints(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_obj = DummyApp(self.temp_dir.name)

        config = {
            "id": "p-hum-api",
            "name": "Printer Humidity Test",
            "ip": "192.168.1.60",
            "access_code": "88887777",
            "serial_number": "01P999",
            "has_ams": True,
            "ams_humidity_idx": 4,
            "ams_temp": 25.0,
        }
        p = BambuPrinter(config, self.app_obj.storage)
        p.ams_humidity_idx = 4
        p.ams_temp = 25.0
        self.app_obj.printers["p-hum-api"] = p

        return create_http_app(self.app_obj)

    async def tearDownAsync(self):
        self.temp_dir.cleanup()

    async def test_get_printers_includes_humidity(self):
        """GET /api/printers returns ams_humidity_idx in JSON response."""
        resp = await self.client.get("/api/printers")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        p = data[0]
        assert p["ams_humidity_idx"] == 4
        assert p["ams_temp"] == 25.0

    async def test_calculate_commercial_with_custom_electricity(self):
        """POST /api/commercial/calculate overrides electricity rate and power watts."""
        payload = {
            "weight_g": 50,
            "time_mins": 60,
            "electricity_rate_uah": 6.00,
            "power_watts": 250,
            "client_order": "Замовлення #777",
        }
        resp = await self.client.post("/api/commercial/calculate", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        c = data["calculation"]
        assert c["electricity_rate_uah"] == 6.00
        assert c["power_watts"] == 250
        # 1 hour * 0.25 kW * 6.00 UAH = 1.50 UAH
        assert c["electricity_cost"] == 1.50
        assert c["client_order"] == "Замовлення #777"

    async def test_export_commercial_pdf_with_custom_electricity(self):
        """GET /api/commercial/export_pdf includes custom electricity rate and power watts."""
        resp = await self.client.get(
            "/api/commercial/export_pdf?weight_g=50&time_mins=60&electricity_rate_uah=6.50&power_watts=300&client_order=TestOrder"
        )
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "application/pdf"
        data = await resp.read()
        assert len(data) > 5000


# ==============================================================================
# 4. VISUAL SPOOL CONTRAST LUMINANCE TEST
# ==============================================================================


def test_luminance_contrast_calculation():
    """Verify the luminance formula used to detect white/light spools in JS."""
    def is_light(hex_color: str) -> bool:
        c = hex_color.lstrip("#")
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
        return luminance > 0.72

    assert is_light("#FFFFFF") is True  # Pure White
    assert is_light("#FAFAFA") is True  # Off white
    assert is_light("#F0E68C") is True  # Khaki / Light yellow
    assert is_light("#000000") is False  # Black
    assert is_light("#3B82F6") is False  # Blue
    assert is_light("#EF4444") is False  # Red
    assert is_light("#10B981") is False  # Green
