"""
Unit tests for Fleet Batch Controls:
- REST API POST /api/fleet/lights
- REST API POST /api/fleet/calibrate
- Telegram Bot Batch Callbacks & Commands
- Model chamber light toggle logic
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import AioHTTPTestCase
import pytest

from bot.handlers.dashboard import (
    handle_callback_batch_calibrate_confirm,
    handle_callback_batch_calibrate_prompt,
    handle_callback_batch_calibrate_cancel,
    handle_callback_batch_light_off,
    handle_callback_batch_light_on,
    handle_text_batch_calibrate,
    handle_text_batch_light_off,
    handle_text_batch_light_on,
)
from bot.keyboards import (
    get_farm_batch_actions_keyboard,
    get_fleet_calibrate_confirm_keyboard,
)
from models.printer import BambuPrinter
from services.http_server import create_http_app
from storage.manager import StorageManager


class MockFleetPrinter:
    def __init__(self, pid: str, name: str, state: str = "IDLE", is_online: bool = True):
        self.id = pid
        self.name = name
        self.gcode_state = state
        self.is_online = is_online
        self.mapped_state = "OFFLINE" if not is_online else ("RUNNING" if state == "RUNNING" else "ONLINE")
        self.is_printing = state in ["RUNNING", "PREPARING", "PAUSE"]
        self.chamber_light_state = "off"
        self.toggle_chamber_light = MagicMock(side_effect=self._mock_toggle_light)
        self.start_calibration = MagicMock(return_value=True)

    def _mock_toggle_light(self, mode: str = "toggle"):
        if mode == "toggle":
            self.chamber_light_state = "off" if self.chamber_light_state == "on" else "on"
        else:
            self.chamber_light_state = "on" if str(mode).lower() in ["on", "1", "true"] else "off"
        return True


class DummyFleetApp:
    def __init__(self, temp_dir: str):
        self.storage = StorageManager(Path(temp_dir))
        self.printers = {}
        self.global_settings = {}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, uid: str):
        return True


class TestFleetHTTPRoutes(AioHTTPTestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = self.temp_dir_obj.name
        import config
        self.orig_storage_dir = config.STORAGE_DIR
        config.STORAGE_DIR = Path(self.temp_dir)
        from services.http.middleware import IP_CONTROL_LOGS, IP_REQUEST_LOGS, IP_UPLOAD_LOGS
        IP_REQUEST_LOGS.clear()
        IP_UPLOAD_LOGS.clear()
        IP_CONTROL_LOGS.clear()
        super().setUp()

    async def tearDownAsync(self):
        if hasattr(self, "client") and self.client:
            await self.client.close()
        await asyncio.sleep(0.02)
        await super().tearDownAsync()

    def tearDown(self):
        import config
        config.STORAGE_DIR = self.orig_storage_dir
        self.temp_dir_obj.cleanup()
        super().tearDown()

    async def get_application(self):
        self.dummy_app = DummyFleetApp(self.temp_dir)
        self.p1 = MockFleetPrinter("p1", "A1 mini 1", state="IDLE", is_online=True)
        self.p2 = MockFleetPrinter("p2", "A1 mini 2", state="RUNNING", is_online=True)
        self.p3 = MockFleetPrinter("p3", "P1S", state="OFFLINE", is_online=False)
        self.p4 = MockFleetPrinter("p4", "A1", state="PAUSE", is_online=True)
        self.dummy_app.printers = {
            "p1": self.p1,
            "p2": self.p2,
            "p3": self.p3,
            "p4": self.p4,
        }
        return create_http_app(self.dummy_app)

    @patch("services.http.routes_control.check_auth", new_callable=AsyncMock, return_value=True)
    async def test_fleet_lights_on(self, mock_auth):
        resp = await self.client.post("/api/fleet/lights", json={"mode": "on"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["mode"], "on")
        # Online printers p1, p2, p4 should be updated (3 printers)
        self.assertEqual(data["updated_count"], 3)
        self.assertEqual(data["skipped_count"], 1)
        self.p1.toggle_chamber_light.assert_called_with("on")
        self.p2.toggle_chamber_light.assert_called_with("on")
        self.p4.toggle_chamber_light.assert_called_with("on")
        self.p3.toggle_chamber_light.assert_not_called()

    @patch("services.http.routes_control.check_auth", new_callable=AsyncMock, return_value=True)
    async def test_fleet_lights_off(self, mock_auth):
        resp = await self.client.post("/api/fleet/lights", json={"mode": "off"})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["mode"], "off")
        self.p1.toggle_chamber_light.assert_called_with("off")

    @patch("services.http.routes_control.check_auth", new_callable=AsyncMock, return_value=True)
    async def test_fleet_calibrate_idle_only(self, mock_auth):
        """Verify calibration only triggers for idle online printers, never busy or offline."""
        resp = await self.client.post("/api/fleet/calibrate", json={})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        # Only p1 is idle and online
        self.assertEqual(data["calibrated_count"], 1)
        self.assertEqual(data["skipped_count"], 3)
        self.p1.start_calibration.assert_called_once()
        self.p2.start_calibration.assert_not_called()
        self.p3.start_calibration.assert_not_called()
        self.p4.start_calibration.assert_not_called()


@pytest.mark.asyncio
async def test_bot_fleet_batch_callbacks_and_messages():
    app = MagicMock()
    app.is_user_approved = AsyncMock(return_value=True)
    app.storage.load_user = AsyncMock(return_value={"language": "uk"})

    p1 = MockFleetPrinter("p1", "A1 mini 1", state="IDLE", is_online=True)
    p2 = MockFleetPrinter("p2", "P1S", state="RUNNING", is_online=True)
    p3 = MockFleetPrinter("p3", "X1C", state="OFFLINE", is_online=False)
    app.printers = {"p1": p1, "p2": p2, "p3": p3}

    # 1. Batch lights on callback
    cb_light_on = AsyncMock()
    cb_light_on.message.chat.id = 12345
    await handle_callback_batch_light_on(cb_light_on, app)
    cb_light_on.answer.assert_called_once()
    assert "2" in cb_light_on.answer.call_args[0][0]  # 2 online printers
    p1.toggle_chamber_light.assert_called_with("on")
    p2.toggle_chamber_light.assert_called_with("on")

    # 2. Batch lights off callback
    cb_light_off = AsyncMock()
    cb_light_off.message.chat.id = 12345
    await handle_callback_batch_light_off(cb_light_off, app)
    cb_light_off.answer.assert_called_once()
    p1.toggle_chamber_light.assert_called_with("off")

    # 3. Batch calibrate prompt callback
    cb_prompt = AsyncMock()
    cb_prompt.message.chat.id = 12345
    await handle_callback_batch_calibrate_prompt(cb_prompt, app)
    cb_prompt.message.reply.assert_called_once()
    cb_prompt.answer.assert_called_once()

    # 4. Batch calibrate confirm callback
    cb_confirm = AsyncMock()
    cb_confirm.message.chat.id = 12345
    await handle_callback_batch_calibrate_confirm(cb_confirm, app)
    cb_confirm.answer.assert_called_once()
    p1.start_calibration.assert_called_once()
    p2.start_calibration.assert_not_called()
    p3.start_calibration.assert_not_called()

    # 5. Text commands
    msg_light = AsyncMock()
    msg_light.chat.id = 12345
    await handle_text_batch_light_on(msg_light, app)
    msg_light.answer.assert_called_once()
    assert "Увімкнено" in msg_light.answer.call_args[0][0]

    msg_cal = AsyncMock()
    msg_cal.chat.id = 12345
    await handle_text_batch_calibrate(msg_cal, app)
    msg_cal.answer.assert_called_once()
    assert "Підтвердження" in msg_cal.answer.call_args[0][0]


def test_printer_model_toggle_chamber_light():
    """Test BambuPrinter.toggle_chamber_light logic fix."""
    p_cfg = {
        "id": "p99",
        "name": "Test P",
        "ip": "192.168.1.99",
        "code": "code",
        "serial": "sn99",
        "model": "A1",
    }
    p = BambuPrinter(p_cfg, storage=MagicMock())
    p._client = MagicMock()
    p._client.is_connected.return_value = True

    # Initial state is "off"
    p.chamber_light_state = "off"
    # Mode "on" turns it "on"
    p.toggle_chamber_light("on")
    assert p.chamber_light_state == "on"

    # Crucial regression test: when chamber_light_state is already "on", mode "on" MUST stay "on"!
    p.toggle_chamber_light("on")
    assert p.chamber_light_state == "on"

    # Mode "off" turns it "off"
    p.toggle_chamber_light("off")
    assert p.chamber_light_state == "off"

    # When state is "off", mode "off" MUST stay "off"
    p.toggle_chamber_light("off")
    assert p.chamber_light_state == "off"

    # Mode "toggle" flips from "off" to "on"
    p.toggle_chamber_light("toggle")
    assert p.chamber_light_state == "on"

    # Mode "toggle" flips from "on" to "off"
    p.toggle_chamber_light("toggle")
    assert p.chamber_light_state == "off"


def test_farm_keyboards():
    """Verify inline keyboards have correct callbacks and structure."""
    kb_uk = get_farm_batch_actions_keyboard("uk")
    buttons_uk = [btn.callback_data for row in kb_uk.inline_keyboard for btn in row]
    assert "batch_light_on" in buttons_uk
    assert "batch_light_off" in buttons_uk
    assert "batch_calibrate_prompt" in buttons_uk

    kb_en = get_farm_batch_actions_keyboard("en")
    texts_en = [btn.text for row in kb_en.inline_keyboard for btn in row]
    assert any("Turn All Lights On" in t for t in texts_en)

    confirm_kb = get_fleet_calibrate_confirm_keyboard("uk")
    confirm_callbacks = [btn.callback_data for row in confirm_kb.inline_keyboard for btn in row]
    assert "batch_calibrate_confirm" in confirm_callbacks
    assert "batch_calibrate_cancel" in confirm_callbacks


@pytest.mark.asyncio
async def test_bot_fleet_batch_cancel_and_off():
    app = MagicMock()
    app.is_user_approved = AsyncMock(return_value=True)
    app.storage.load_user = AsyncMock(return_value={"language": "en"})

    p1 = MockFleetPrinter("p1", "A1 mini", state="IDLE", is_online=True)
    app.printers = {"p1": p1}

    # Cancel callback
    cb_cancel = AsyncMock()
    cb_cancel.message.chat.id = 12345
    await handle_callback_batch_calibrate_cancel(cb_cancel, app)
    cb_cancel.answer.assert_called_once()
    cb_cancel.message.delete.assert_called_once()

    # Text command light off
    msg_off = AsyncMock()
    msg_off.chat.id = 12345
    await handle_text_batch_light_off(msg_off, app)
    msg_off.answer.assert_called_once()
    assert "Turned off" in msg_off.answer.call_args[0][0]
    p1.toggle_chamber_light.assert_called_with("off")
