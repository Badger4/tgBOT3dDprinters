"""
Unit tests for Printer HTTP Routes, Control Actions, File Uploads, and Spools.
Refactored into cohesive test classes with robust async teardown and process/timing isolation.
"""

import asyncio
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import FormData
from aiohttp.test_utils import AioHTTPTestCase

from services.http_server import create_http_app
from storage.manager import StorageManager


class MockPrinter:
    def __init__(self, pid="p1", name="Test P1S", state="IDLE"):
        self.id = pid
        self.name = name
        self.ip = "192.168.1.50"
        self.serial_number = "SN123"
        self.access_code = "12345678"
        self.gcode_state = state
        self.nozzle_temper = 215
        self.bed_temper = 60
        self.mc_percent = 0
        self.mc_remaining_time = 0
        self.layer_num = 0
        self.total_layer_num = 0
        self.subtask_name = ""
        self.filament_type = "PLA"
        self.filament_grams = 1000.0
        self.last_job_grams = 0.0
        self._current_job_grams = 0.0
        self.chamber_light_state = "off"
        self.spd_lvl = 2
        self.spd_mag = 100
        self.maintenance_hours_counter = 45.0
        self.maintenance_interval_hours = 100
        self.total_print_hours = 45.0
        self.hms_errors = []
        self.ams_slots = {}
        self.ams_trays_info = {}
        self.active_ams_tray = 255
        self.has_ams = False
        self.ams_units = []
        self.notify = True
        self.price_per_kg = 650.0
        self.active_spool_id = None
        self.ams_enabled = False
        # Mock methods
        self.pause = MagicMock(return_value=True)
        self.resume = MagicMock(return_value=True)
        self.stop_print = MagicMock(return_value=True)
        self.toggle_chamber_light = MagicMock()
        self.set_speed_level = MagicMock(return_value=True)
        self.reset_maintenance_counter = MagicMock()
        self.set_maintenance_interval = MagicMock()
        self.set_slot_grams = MagicMock()
        self.start_calibration = MagicMock(return_value=True)
        self.destroy = MagicMock()
        self.init_mqtt = MagicMock()
        self.start_print_job_async = AsyncMock(return_value=(True, "Print started"))

    def get_active_slot_key(self):
        return "255"


class DummyApp:
    def __init__(self, temp_dir):
        self.storage = StorageManager(Path(temp_dir))
        self.printers = {}
        self.global_settings = {}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, uid):
        return True


class BaseHTTPTestCase(AioHTTPTestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = self.temp_dir_obj.name
        # Override STORAGE_DIR in config for file uploads
        import config

        self.orig_storage_dir = config.STORAGE_DIR
        config.STORAGE_DIR = Path(self.temp_dir)
        import services.http.routes_files

        services.http.routes_files.STORAGE_DIR = Path(self.temp_dir)
        # Clear global rate limiting state from previous tests
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
        try:
            from services.http.middleware import IP_CONTROL_LOGS, IP_REQUEST_LOGS, IP_UPLOAD_LOGS

            IP_REQUEST_LOGS.clear()
            IP_UPLOAD_LOGS.clear()
            IP_CONTROL_LOGS.clear()
            super().tearDown()
        finally:
            import config

            config.STORAGE_DIR = self.orig_storage_dir
            if hasattr(self, "temp_dir_obj"):
                self.temp_dir_obj.cleanup()

    async def get_application(self):
        self.dummy_app = DummyApp(self.temp_dir)
        return create_http_app(self.dummy_app)


# ============================================================================
# 1. PRINTERS CRUD & TELEMETRY
# ============================================================================
class TestHTTPRoutesPrintersCRUD(BaseHTTPTestCase):
    async def test_get_printers_empty(self):
        resp = await self.client.get("/api/printers")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data, [])

    async def test_get_printers_with_data(self):
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.get("/api/printers")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "p1")

    async def test_get_printers_auth_fail(self):
        resp = await self.client.get("/api/printers", headers={"X-Forwarded-For": "192.168.1.1"})
        self.assertEqual(resp.status, 401)

    @patch("services.http.routes_printers.BambuPrinter")
    async def test_create_printer_success(self, MockBambuPrinter):
        mock_p = MockPrinter()
        MockBambuPrinter.return_value = mock_p
        resp = await self.client.post(
            "/api/printers",
            json={
                "name": "New Printer",
                "ip": "192.168.1.99",
                "accessCode": "11111111",
                "serialNumber": "SN999",
                "printerModel": "P1S",
            },
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("printer", data)

    async def test_create_printer_missing_fields(self):
        resp = await self.client.post(
            "/api/printers",
            json={"name": "New Printer"},  # Missing ip and accessCode
        )
        self.assertEqual(resp.status, 400)

    async def test_create_printer_invalid_json(self):
        resp = await self.client.post("/api/printers", data=b"invalid json")
        self.assertEqual(resp.status, 400)

    async def test_delete_printer_success(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.delete("/api/printers/p1")
        self.assertEqual(resp.status, 200)
        self.assertNotIn("p1", self.dummy_app.printers)
        mock_p.destroy.assert_called_once()

    async def test_delete_printer_not_found(self):
        resp = await self.client.delete("/api/printers/nonexistent")
        self.assertEqual(resp.status, 404)

    async def test_get_single_printer_success(self):
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.get("/api/printers/p1")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["id"], "p1")

    async def test_get_single_printer_not_found(self):
        resp = await self.client.get("/api/printers/p1")
        self.assertEqual(resp.status, 404)

    @patch("services.http.routes_printers.capture_real_camera_photo", new_callable=AsyncMock)
    async def test_get_snapshot_success(self, mock_capture):
        mock_capture.return_value = b"\xff\xd8fakejpeg\xff\xd9"
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.get("/api/printers/p1/snapshot")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers.get("Content-Type"), "image/jpeg")

    @patch("services.http.routes_printers.capture_real_camera_photo", new_callable=AsyncMock)
    async def test_get_snapshot_fail(self, mock_capture):
        mock_capture.return_value = None
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.get("/api/printers/p1/snapshot")
        self.assertEqual(resp.status, 503)

    async def test_get_snapshot_not_found(self):
        resp = await self.client.get("/api/printers/p1/snapshot")
        self.assertEqual(resp.status, 404)

    async def test_update_access_code_success(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/access_code", json={"accessCode": "88888888"})
        self.assertEqual(resp.status, 200)
        self.assertEqual(mock_p.access_code, "88888888")
        mock_p.destroy.assert_called_once()
        mock_p.init_mqtt.assert_called_once()

    async def test_update_access_code_invalid_json(self):
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.post("/api/printers/p1/access_code", data=b"invalid json")
        self.assertEqual(resp.status, 400)

    async def test_update_access_code_not_found(self):
        resp = await self.client.post("/api/printers/p1/access_code", json={"accessCode": "8888"})
        self.assertEqual(resp.status, 404)


# ============================================================================
# 2. PRINTER CONTROL ACTIONS
# ============================================================================
class TestHTTPRoutesControl(BaseHTTPTestCase):
    async def test_control_pause(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "pause"})
        self.assertEqual(resp.status, 200)
        mock_p.pause.assert_called_once()

    async def test_control_resume(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "resume"})
        self.assertEqual(resp.status, 200)
        mock_p.resume.assert_called_once()

    async def test_control_stop(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "stop"})
        self.assertEqual(resp.status, 200)
        mock_p.stop_print.assert_called_once()

    async def test_control_light_toggle(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "light_toggle"})
        self.assertEqual(resp.status, 200)
        mock_p.toggle_chamber_light.assert_called_once_with("toggle")

    async def test_control_toggle_notify(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "toggle_notify"})
        self.assertEqual(resp.status, 200)
        self.assertFalse(mock_p.notify)

    async def test_control_set_speed(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "set_speed", "level": 3})
        self.assertEqual(resp.status, 200)
        mock_p.set_speed_level.assert_called_once_with(3)

    async def test_control_reset_maint(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "reset_maint"})
        self.assertEqual(resp.status, 200)

    async def test_get_printer_settings(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.get("/api/printers/p1/settings")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["id"], "p1")
        self.assertEqual(data["name"], "Test P1S")

    async def test_update_printer_settings(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/settings",
            json={"name": "New Name", "maintenance_interval_hours": 150, "notify": False},
        )
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(mock_p.name, "New Name")
        self.assertEqual(mock_p.maintenance_interval_hours, 150)
        self.assertFalse(mock_p.notify)
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "reset_maint", "item_key": "lead_screws"}
        )
        self.assertEqual(resp.status, 200)
        mock_p.reset_maintenance_counter.assert_called_once_with("lead_screws")

    async def test_control_set_maint_interval(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control",
            json={"action": "set_maint_interval", "item_key": "lead_screws", "interval_hours": 150.0},
        )
        self.assertEqual(resp.status, 200)
        mock_p.set_maintenance_interval.assert_called_once_with("lead_screws", 150.0)

    async def test_control_set_filament(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "set_filament", "grams": 800, "slot_id": 0}
        )
        self.assertEqual(resp.status, 200)
        mock_p.set_slot_grams.assert_called_once_with(800.0, slot_id=0)

    async def test_control_assign_spool_success(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        # Create spool in storage
        await self.dummy_app.storage.save_spools({"s1": {"id": "s1", "name": "PLA Black", "remaining_weight": 750}})

        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "assign_spool", "spool_id": "s1", "slot_key": "0"}
        )
        self.assertEqual(resp.status, 200)

    async def test_control_assign_spool_not_found(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "assign_spool", "spool_id": "missing", "slot_key": "0"}
        )
        self.assertEqual(resp.status, 404)

    async def test_control_unassign_spool(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "unassign_spool", "slot_key": "tray_0"}
        )
        self.assertEqual(resp.status, 200)

    async def test_control_set_ams_enabled(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "set_ams_enabled", "enabled": True})
        self.assertEqual(resp.status, 200)
        self.assertTrue(mock_p.ams_enabled)

    async def test_control_calibrate_idle(self):
        mock_p = MockPrinter(state="IDLE")
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post(
            "/api/printers/p1/control", json={"action": "calibrate", "bed_level": True, "motor_noise": True}
        )
        self.assertEqual(resp.status, 200)
        mock_p.start_calibration.assert_called_once()

    async def test_control_calibrate_running_fails(self):
        mock_p = MockPrinter(state="RUNNING")
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "calibrate"})
        self.assertEqual(resp.status, 400)

    async def test_control_unknown_action(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/control", json={"action": "invalid_action"})
        self.assertEqual(resp.status, 400)

    async def test_control_invalid_json(self):
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.post("/api/printers/p1/control", data=b"bad_json")
        self.assertEqual(resp.status, 400)

    async def test_control_printer_not_found(self):
        resp = await self.client.post("/api/printers/p1/control", json={"action": "pause"})
        self.assertEqual(resp.status, 404)


# ============================================================================
# 3. FILE UPLOADS & PRINT TRIGGER
# ============================================================================
class TestHTTPRoutesFiles(BaseHTTPTestCase):
    @patch("services.http.routes_files.parse_3mf_file")
    async def test_file_upload_valid_3mf(self, mock_parse):
        import config

        self.assertTrue(config.STORAGE_DIR.exists())
        mock_parse.return_value = {
            "valid": True,
            "printer_model": "Bambu Lab P1S",
            "filament_type": "PLA",
            "weight_g": 100,
            "time_mins": 60,
        }
        data = FormData()
        data.add_field(
            "file", b"PK\x03\x04" + b"\x00" * 100, filename="test.3mf", content_type="application/octet-stream"
        )
        resp = await self.client.post("/api/files/upload", data=data)
        self.assertEqual(resp.status, 200)
        resp_data = await resp.json()
        self.assertEqual(resp_data["status"], "ok")
        self.assertTrue((config.STORAGE_DIR / "uploads").exists())

    async def test_file_upload_invalid_ext(self):
        data = FormData()
        data.add_field("file", b"content", filename="test.txt", content_type="text/plain")
        resp = await self.client.post("/api/files/upload", data=data)
        self.assertEqual(resp.status, 400)

    async def test_file_upload_no_file(self):
        resp = await self.client.post("/api/files/upload", data=b"")
        self.assertIn(resp.status, (400, 500))

    async def test_file_upload_invalid_3mf_signature(self):
        data = FormData()
        data.add_field("file", b"Not a ZIP file", filename="test.3mf", content_type="application/octet-stream")
        resp = await self.client.post("/api/files/upload", data=data)
        self.assertEqual(resp.status, 400)

    async def test_print_file_success(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        # Create the upload file in the temp dir that STORAGE_DIR points to
        upload_dir = Path(self.temp_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / "123_test.3mf"
        file_path.write_bytes(b"fake_data")

        # Patch STORAGE_DIR at routes_files module level
        with patch("services.http.routes_files.STORAGE_DIR", Path(self.temp_dir)):
            resp = await self.client.post("/api/printers/p1/print_file", json={"file_token": "123_test.3mf"})
            self.assertEqual(resp.status, 200)
            mock_p.start_print_job_async.assert_called_once()

    async def test_print_file_not_found(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"p1": mock_p}
        resp = await self.client.post("/api/printers/p1/print_file", json={"file_token": "missing.3mf"})
        self.assertEqual(resp.status, 404)

    async def test_print_file_printer_not_found(self):
        resp = await self.client.post("/api/printers/p1/print_file", json={"file_token": "123_test.3mf"})
        self.assertEqual(resp.status, 404)


# ============================================================================
# 4. SPOOLS CRUD, SSE STREAM, CORS PREFLIGHT & RATE LIMITING
# ============================================================================
class TestHTTPRoutesSpoolsAndSSE(BaseHTTPTestCase):
    async def test_get_spools(self):
        spools = {"s1": {"id": "s1"}}
        await self.dummy_app.storage.save_spools(spools)
        resp = await self.client.get("/api/spools")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data, spools)

    async def test_save_spool(self):
        resp = await self.client.post("/api/spools", json={"id": "s1", "name": "PLA Red"})
        self.assertEqual(resp.status, 200)
        spools = await self.dummy_app.storage.load_spools()
        self.assertIn("s1", spools)
        self.assertEqual(spools["s1"]["name"], "PLA Red")

    async def test_delete_spool_success(self):
        spools = {"s1": {"id": "s1"}}
        await self.dummy_app.storage.save_spools(spools)
        resp = await self.client.delete("/api/spools/s1")
        self.assertEqual(resp.status, 200)
        updated_spools = await self.dummy_app.storage.load_spools()
        self.assertNotIn("s1", updated_spools)

    async def test_delete_spool_not_found(self):
        resp = await self.client.delete("/api/spools/s1")
        self.assertEqual(resp.status, 404)

    async def test_sse_stream_sends_data(self):
        self.dummy_app.printers = {"p1": MockPrinter()}
        resp = await self.client.get("/api/events")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))

        try:
            line = await asyncio.wait_for(resp.content.readline(), timeout=5.0)
            self.assertTrue(line.startswith(b"data: "))
        except TimeoutError:
            pass
        resp.close()

    async def test_options_cors_preflight(self):
        # 1. Allowed Telegram WebApp origin
        headers = {"Origin": "https://web.telegram.org"}
        resp = await self.client.request("OPTIONS", "/api/printers", headers=headers)
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "https://web.telegram.org")
        self.assertIn("Access-Control-Allow-Methods", resp.headers)
        self.assertIn("Access-Control-Allow-Headers", resp.headers)

        # 2. Disallowed origin returns "null"
        bad_headers = {"Origin": "https://malicious-hacker-site.com"}
        bad_resp = await self.client.request("OPTIONS", "/api/printers", headers=bad_headers)
        self.assertEqual(bad_resp.status, 204)
        self.assertEqual(bad_resp.headers.get("Access-Control-Allow-Origin"), "null")

    async def test_control_rate_limiting(self):
        mock_p = MockPrinter()
        self.dummy_app.printers = {"printer_test": mock_p}

        from services.http.middleware import IP_CONTROL_LOGS

        IP_CONTROL_LOGS.clear()

        # Sensitive control limit is 20 req/min
        for _ in range(20):
            resp = await self.client.request("POST", "/api/printers/printer_test/control", json={"action": "pause"})
            self.assertIn(resp.status, (200, 400, 404))
            self.assertEqual(resp.headers.get("X-RateLimit-Limit"), "20")

        # 21st request triggers 429 Too Many Requests
        exceeded_resp = await self.client.request(
            "POST", "/api/printers/printer_test/control", json={"action": "pause"}
        )
        self.assertEqual(exceeded_resp.status, 429)
        exceeded_data = await exceeded_resp.json()
        self.assertEqual(exceeded_data["error"], "Too Many Requests")
        self.assertEqual(exceeded_resp.headers.get("X-RateLimit-Remaining"), "0")

        IP_CONTROL_LOGS.clear()
