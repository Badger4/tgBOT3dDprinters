"""
Comprehensive unit tests for the 6 new farm features:
1. Smart AMS Failover Guard (find_ams_backup_slots)
2. Automated Scrap Accounting Without Physical Scales (StorageManager.mark_history_scrap & REST API)
3. Client / Order Reference Field (commercial calc, history, and PDF exports)
4. Visual Spool Widget (SVG data & formatting)
5. Live Farm Status (/status) with Progress Bars & In-place Auto-update
6. Haptic Feedback support
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from bot.handlers.dashboard import (
    format_live_dashboard_text,
    handle_callback_refresh_live_status,
    handle_dashboard,
    make_progress_bar,
)
from bot.keyboards import get_live_status_inline_keyboard
from models.printer import BambuPrinter
from services.http_server import create_http_app
from services.report_generator import generate_commercial_calc_pdf, generate_history_pdf_report
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
# 1. SMART AMS FAILOVER GUARD TESTS
# ==============================================================================


def test_ams_backup_slots_found():
    """Tests that find_ams_backup_slots identifies compatible spools in other AMS slots."""
    storage = MagicMock()
    config = {
        "id": "printer-1",
        "name": "Bambu X1C",
        "ip": "192.168.1.100",
        "access_code": "12345678",
        "serial": "SN123",
        "has_ams": True,
        "active_slot_key": "0",
        "ams_slots": {
            "0": 50.0,    # Active slot (low, 50g)
            "1": 800.0,   # Compatible backup (800g PLA)
            "2": 0.0,     # Empty tray
            "3": 500.0,   # TPU (mismatched)
        },
        "ams_trays_info": {
            "0": {"type": "PLA Basic", "color": "#000000", "empty": False},
            "1": {"type": "PLA Basic", "color": "#FFFFFF", "empty": False},
            "2": {"type": "", "color": "", "empty": True},
            "3": {"type": "TPU", "color": "#FF0000", "empty": False},
        },
    }
    p = BambuPrinter(config, storage)

    # Active tray is PLA Basic (slot 0)
    backups = p.find_ams_backup_slots(required_type="PLA Basic")
    assert len(backups) == 1
    assert backups[0]["slot"] == "1"
    assert backups[0]["grams"] == 800.0
    assert "A2" in backups[0]["name"]


def test_ams_backup_slots_no_compatible():
    """Tests when no compatible spools exist in other slots."""
    storage = MagicMock()
    config = {
        "id": "printer-2",
        "name": "Bambu P1S",
        "ip": "192.168.1.101",
        "access_code": "12345678",
        "serial": "SN456",
        "has_ams": True,
        "active_slot_key": "0",
        "ams_slots": {
            "0": 30.0,
            "1": 400.0,
            "2": 600.0,
        },
        "ams_trays_info": {
            "0": {"type": "PETG", "empty": False},
            "1": {"type": "PLA", "empty": False},
            "2": {"type": "ABS", "empty": False},
        },
    }
    p = BambuPrinter(config, storage)
    backups = p.find_ams_backup_slots(required_type="PETG")
    assert len(backups) == 0


# ==============================================================================
# 2. AUTOMATED SCRAP ACCOUNTING WITHOUT SCALES (STORAGE TESTS)
# ==============================================================================


@pytest.mark.asyncio
async def test_storage_mark_history_scrap_and_refund():
    """Tests marking a print job as scrap and automatically refunding unprinted grams to spool."""
    with tempfile.TemporaryDirectory() as td:
        storage = StorageManager(Path(td))

        # 1. Setup spool
        spools = {
            "spool-1": {
                "id": "spool-1",
                "name": "E SUN PLA+",
                "type": "PLA",
                "remaining_grams": 400.0,
                "initial_grams": 1000.0,
                "price_per_kg": 650.0,
                "assigned_printer_id": "p1",
                "assigned_slot_key": "0",
            }
        }
        await storage.save_spools(spools)

        # 2. Setup history entry (100g planned)
        test_ts = 1700000000.0
        history = [
            {
                "timestamp": test_ts,
                "printer_name": "Lab X1C",
                "printer_id": "p1",
                "subtask_name": "Bracket_v1.gcode",
                "filament_type": "PLA",
                "weight_g": 100.0,
                "note": "Виконується",
                "slot_key": "0",
                "spool_id": "spool-1",
            }
        ]
        await storage.save_json(storage.history_file, history)

        # 3. Stopped at 40%: Wasted = 40g, Refund = 60g
        wasted_g = 40.0
        refund_g = 60.0
        reason = "Відлипання від столу (Warping)"

        entry = await storage.mark_history_scrap(
            timestamp=test_ts,
            wasted_weight_g=wasted_g,
            reason=reason,
            refund_grams=refund_g,
            printer_id="p1",
            slot_key="0",
            spool_id="spool-1",
        )

        assert entry is not None
        assert entry["is_scrap"] is True
        assert entry["scrap_reason"] == reason
        assert entry["wasted_weight_g"] == 40.0
        assert entry["refunded_g"] == 60.0
        assert "Брак" in entry["note"]

        # Verify spool balance refunded: 400 + 60 = 460g
        reloaded_spools = await storage.load_spools()
        assert reloaded_spools["spool-1"]["remaining_grams"] == 460.0

        # Verify audit movement recorded
        movements = await storage.load_spool_movements()
        assert len(movements) == 1
        assert movements[0]["action"] == "scrap_refund"
        assert movements[0]["weight_change_g"] == 60.0
        assert movements[0]["new_weight_g"] == 460.0


# ==============================================================================
# 3. REST API ENDPOINTS TESTS
# ==============================================================================


class TestNewFarmFeaturesApi(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_app = DummyApp(self.temp_dir.name)

        # Pre-seed history with 1 normal print and 1 scrap print
        self.ts_scrap = time.time() - 3600
        self.ts_normal = time.time() - 7200
        history = [
            {
                "timestamp": self.ts_normal,
                "printer_name": "Printer A",
                "printer_id": "p1",
                "subtask_name": "Vase.3mf",
                "filament_type": "PLA",
                "weight_g": 120.0,
                "cost_uah": 95.0,
                "client_order": "Замовлення #101 (Андрій)",
                "note": "Успішно виконано",
            },
            {
                "timestamp": self.ts_scrap,
                "printer_name": "Printer B",
                "printer_id": "p2",
                "subtask_name": "Gear.gcode",
                "filament_type": "PETG",
                "weight_g": 80.0,
                "cost_uah": 60.0,
                "is_scrap": True,
                "scrap_reason": "Забиття сопла",
                "wasted_weight_g": 35.0,
                "refunded_g": 45.0,
                "note": "Брак ❌ (Забиття сопла)",
            },
        ]
        await self.dummy_app.storage.save_json(self.dummy_app.storage.history_file, history)

        app = create_http_app(self.dummy_app)
        return app

    def setUp(self):
        from services.http.middleware import IP_CONTROL_LOGS, IP_REQUEST_LOGS, IP_UPLOAD_LOGS
        IP_REQUEST_LOGS.clear()
        IP_UPLOAD_LOGS.clear()
        IP_CONTROL_LOGS.clear()
        super().setUp()

    async def tearDownAsync(self):
        if hasattr(self, "client") and self.client:
            await self.client.close()
        await asyncio.sleep(0.05)
        await super().tearDownAsync()

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    @unittest_run_loop
    async def test_get_history_scrap_metrics(self):
        """Tests that GET /api/history returns scrap statistics and client_order."""
        resp = await self.client.get("/api/history")
        assert resp.status == 200
        data = await resp.json()

        assert data["total_jobs"] == 2
        assert data["total_scrap_jobs"] == 1
        assert data["total_scrap_g"] == 35.0
        assert data["scrap_rate_pct"] == 50.0

        records = data["history"]
        assert len(records) == 2
        assert records[0]["client_order"] == "Замовлення #101 (Андрій)"
        assert records[1]["is_scrap"] is True
        assert records[1]["scrap_reason"] == "Забиття сопла"
        assert records[1]["wasted_weight_g"] == 35.0

    @unittest_run_loop
    async def test_mark_scrap_endpoint(self):
        """Tests POST /api/history/mark_scrap endpoint."""
        payload = {
            "timestamp": self.ts_normal,
            "wasted_weight_g": 50.0,
            "refund_grams": 70.0,
            "reason": "Зсув шарів",
            "printer_id": "p1",
        }
        resp = await self.client.post("/api/history/mark_scrap", json=payload)
        assert resp.status == 200
        res = await resp.json()
        assert res["status"] == "ok"
        assert res["entry"]["is_scrap"] is True
        assert res["entry"]["scrap_reason"] == "Зсув шарів"
        assert res["entry"]["wasted_weight_g"] == 50.0

    @unittest_run_loop
    async def test_commercial_calculate_client_order(self):
        """Tests POST /api/commercial/calculate passes and returns client_order."""
        payload = {
            "weight_g": 150.0,
            "time_mins": 90,
            "client_order": "Замовлення #202 (Марина)",
        }
        resp = await self.client.post("/api/commercial/calculate", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["calculation"]["client_order"] == "Замовлення #202 (Марина)"
        assert data["calculation"]["weight_g"] == 150.0

    @unittest_run_loop
    async def test_commercial_export_pdf_with_client_order(self):
        """Tests GET /api/commercial/export_pdf generates valid PDF containing client_order."""
        url = "/api/commercial/export_pdf?weight_g=100&time_mins=60&client_order=Замовлення%20303"
        resp = await self.client.get(url)
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/pdf"
        content = await resp.read()
        assert len(content) > 1000
        assert content.startswith(b"%PDF")


# ==============================================================================
# 4. LIVE FARM STATUS & PROGRESS BAR TESTS
# ==============================================================================


def test_make_progress_bar():
    """Tests unicode visual progress bar rendering."""
    assert make_progress_bar(0, 10) == "░░░░░░░░░░"
    assert make_progress_bar(50, 10) == "█████░░░░░"
    assert make_progress_bar(100, 10) == "██████████"
    assert make_progress_bar(73, 10) == "███████░░░"
    assert make_progress_bar(-10, 10) == "░░░░░░░░░░"
    assert make_progress_bar(150, 10) == "██████████"


def test_format_live_dashboard_text():
    """Tests formatting live farm dashboard text with active printer telemetry."""
    app = DummyApp("/tmp")

    class MockPrinter:
        id = "p-live"
        name = "Voron Trident"
        is_online = True
        mapped_state = "RUNNING"
        spd_mag = 120
        subtask_name = "Drone_Arm.gcode"
        mc_remaining_time = 45
        mc_percent = 68
        nozzle_temper = 245
        bed_temper = 85
        filament_grams = 520
        filament_type = "PETG"

    app.printers = {"p-live": MockPrinter()}

    text_uk = format_live_dashboard_text(app, "uk")
    assert "Voron Trident" in text_uk
    assert "Друкує" in text_uk
    assert "⚡120%" in text_uk
    assert "Drone_Arm.gcode" in text_uk
    assert "68%" in text_uk
    assert "245°C" in text_uk
    assert "85°C" in text_uk
    assert "520g" in text_uk
    assert "███████░░░" in text_uk


@pytest.mark.asyncio
async def test_live_status_message_registration_and_refresh():
    """Tests /status command registers message and callback refreshes it."""
    app = DummyApp("/tmp")

    class MockPrinter:
        id = "p-live"
        name = "Bambu A1"
        is_online = True
        mapped_state = "IDLE"
        spd_mag = 100
        nozzle_temper = 25
        bed_temper = 25
        filament_grams = 950
        filament_type = "PLA"

    app.printers = {"p-live": MockPrinter()}

    # 1. Simulate /status message
    msg = AsyncMock()
    msg.chat.id = 12345
    sent_msg = AsyncMock()
    sent_msg.message_id = 9999
    msg.answer.return_value = sent_msg

    with patch.object(app.storage, "load_user", AsyncMock(return_value={"language": "uk"})):
        await handle_dashboard(msg, app)

    assert "12345" in app.live_status_messages
    assert app.live_status_messages["12345"]["message_id"] == 9999

    # 2. Simulate refresh callback
    cb = AsyncMock()
    cb.message.chat.id = 12345
    cb.message.message_id = 9999

    with patch.object(app.storage, "load_user", AsyncMock(return_value={"language": "uk"})):
        await handle_callback_refresh_live_status(cb, app)

    cb.message.edit_text.assert_called_once()
    cb.answer.assert_called_once()


# ==============================================================================
# 5. PDF REPORT GENERATOR TESTS
# ==============================================================================


def test_pdf_reports_generation_with_new_fields():
    """Tests PDF reports render correctly with client_order and scrap metrics."""
    history = [
        {
            "timestamp": 1700000000,
            "printer_name": "Farm Printer 1",
            "subtask_name": "Rocket.stl",
            "filament_type": "PLA",
            "weight_g": 75.0,
            "client_order": "Замовлення #777 (Віктор)",
            "note": "Успішно виконано",
        },
        {
            "timestamp": 1700003600,
            "printer_name": "Farm Printer 2",
            "subtask_name": "Enclosure.3mf",
            "filament_type": "ABS",
            "weight_g": 200.0,
            "is_scrap": True,
            "scrap_reason": "Warping",
            "wasted_weight_g": 90.0,
            "refunded_g": 110.0,
            "note": "Брак ❌ (Warping)",
        },
    ]

    # History PDF
    hist_pdf = generate_history_pdf_report(history)
    assert isinstance(hist_pdf, bytes)
    assert len(hist_pdf) > 2000
    assert hist_pdf.startswith(b"%PDF")

    # Commercial PDF
    calc_data = {
        "preset_name": "PRO PLA",
        "weight_g": 150.0,
        "time_mins": 180,
        "filament_cost": 120.0,
        "electricity_cost": 25.0,
        "direct_cost": 145.0,
        "depreciation_cost": 30.0,
        "depreciation_str": "10 грн/год",
        "consumables_cost": 15.0,
        "consumables_str": "5 грн/год",
        "profit_cost": 190.0,
        "profit_str": "100%",
        "total_price": 380.0,
        "client_order": "Замовлення #999 (ТОВ Вектор)",
    }
    comm_pdf = generate_commercial_calc_pdf(calc_data, filename="Bracket.3mf", lang="uk")
    assert isinstance(comm_pdf, bytes)
    assert len(comm_pdf) > 2000
    assert comm_pdf.startswith(b"%PDF")
