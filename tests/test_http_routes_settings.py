import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from services.http_server import create_http_app
from storage.manager import StorageManager


class DummyApp:
    def __init__(self, temp_dir):
        self.storage = StorageManager(Path(temp_dir))
        self.printers = {}
        self.global_settings = {"notify_start": True, "notify_finish": True}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, uid):
        return True


class TestHttpRoutesSettings(AioHTTPTestCase):
    def setUp(self):
        from services.http.middleware import IP_CONTROL_LOGS, IP_REQUEST_LOGS, IP_UPLOAD_LOGS

        IP_REQUEST_LOGS.clear()
        IP_UPLOAD_LOGS.clear()
        IP_CONTROL_LOGS.clear()
        super().setUp()

    async def get_application(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_app = DummyApp(self.temp_dir.name)

        web_app = create_http_app(self.dummy_app)
        return web_app

    def tearDown(self):
        from services.http.middleware import IP_CONTROL_LOGS, IP_REQUEST_LOGS, IP_UPLOAD_LOGS

        IP_REQUEST_LOGS.clear()
        IP_UPLOAD_LOGS.clear()
        IP_CONTROL_LOGS.clear()
        super().tearDown()
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    @unittest_run_loop
    async def test_health_empty(self):
        resp = await self.client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["total_printers"] == 0
        assert data["active_printers"] == 0
        assert "uptime_seconds" in data
        assert "version" in data

    @unittest_run_loop
    async def test_health_with_printer(self):
        printer = MagicMock()
        printer.gcode_state = "RUNNING"
        self.dummy_app.printers["p1"] = printer

        resp = await self.client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["total_printers"] == 1
        assert data["active_printers"] == 1

    @unittest_run_loop
    @patch("services.http.routes_settings.WEBAPP_DIR")
    async def test_index_missing(self, mock_dir):
        mock_dir.return_value = Path("nonexistent")
        resp = await self.client.get("/")
        assert resp.status == 404

    @unittest_run_loop
    @patch("services.http.routes_settings.WEBAPP_DIR")
    async def test_index_exists(self, mock_dir):
        index_file = Path(self.temp_dir.name) / "index.html"
        index_file.write_text("hello", encoding="utf-8")

        mock_dir.__truediv__.return_value = index_file

        resp = await self.client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert text == "hello"

    @unittest_run_loop
    async def test_get_presets_empty(self):
        resp = await self.client.get("/api/commercial/presets")
        assert resp.status == 200
        data = await resp.json()
        assert "default_pla" in data
        assert "default_petg" in data

    @unittest_run_loop
    async def test_post_preset(self):
        payload = {
            "name": "Test Preset",
            "price_per_g": 1.5,
            "electricity_rate_uah": 5.0,
            "power_watts": 200.0,
            "depreciation_val": "20",
            "consumables_val": "10",
            "profit_val": "150%",
        }
        resp = await self.client.post("/api/commercial/presets", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["preset"]["name"] == "Test Preset"

        resp2 = await self.client.get("/api/commercial/presets")
        data2 = await resp2.json()
        assert data["preset"]["id"] in data2

    @unittest_run_loop
    async def test_post_preset_invalid_numbers(self):
        payload = {"name": "Bad Nums", "price_per_g": "abc", "electricity_rate_uah": None, "power_watts": []}
        resp = await self.client.post("/api/commercial/presets", json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert data["preset"]["price_per_g"] == 0.85
        assert data["preset"]["electricity_rate_uah"] == 4.32
        assert data["preset"]["power_watts"] == 120.0

    @unittest_run_loop
    async def test_delete_preset_success(self):
        await self.client.get("/api/commercial/presets")

        resp = await self.client.delete("/api/commercial/presets/default_pla")
        assert resp.status == 200

        resp2 = await self.client.get("/api/commercial/presets")
        data2 = await resp2.json()
        assert "default_pla" not in data2

    @unittest_run_loop
    async def test_delete_preset_not_found(self):
        resp = await self.client.delete("/api/commercial/presets/notfound")
        assert resp.status == 404

    @unittest_run_loop
    @patch("services.http.routes_settings.calculate_commercial_price")
    async def test_calculate_commercial(self, mock_calc):
        mock_calc.return_value = {"total_price": 100.0}

        resp = await self.client.post(
            "/api/commercial/calculate", json={"weight_g": 50.0, "time_mins": 30, "preset_id": "default_pla"}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["calculation"]["total_price"] == 100.0
        mock_calc.assert_called_once()

    @unittest_run_loop
    async def test_get_history_empty(self):
        resp = await self.client.get("/api/history")
        assert resp.status == 200
        data = await resp.json()
        assert data["total_jobs"] == 0
        assert data["total_weight_kg"] == 0.0
        assert data["history"] == []

    @unittest_run_loop
    async def test_get_history_with_data(self):
        history_data = [{"weight_g": 1000.0, "cost_uah": 500.0}, {"weight_g": 500.0, "cost_uah": 250.0}]
        await self.dummy_app.storage.save_json(self.dummy_app.storage.history_file, history_data)

        resp = await self.client.get("/api/history")
        assert resp.status == 200
        data = await resp.json()
        assert data["total_jobs"] == 2
        assert data["total_weight_kg"] == 1.5
        assert data["total_cost_uah"] == 750.0

    @unittest_run_loop
    async def test_export_history_csv(self):
        history_data = [
            {
                "weight_g": 1000.0,
                "cost_uah": 500.0,
                "printer_name": "P1",
                "subtask_name": "Model",
                "filament_type": "PLA",
                "timestamp": int(time.time()),
            }
        ]
        await self.dummy_app.storage.save_json(self.dummy_app.storage.history_file, history_data)

        resp = await self.client.get("/api/history/export")
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "text/csv"
        assert "Content-Disposition" in resp.headers

        text = await resp.text()
        assert "Дата,Принтер,Модель,Вага (г),Матеріал,Собівартість (грн)" in text
        assert '"P1","Model",1000.0,"PLA",500.0' in text

    @unittest_run_loop
    async def test_get_settings(self):
        resp = await self.client.get("/api/settings")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"notify_start": True, "notify_finish": True}

    @unittest_run_loop
    async def test_update_settings(self):
        resp = await self.client.post("/api/settings", json={"notify_start": False})
        assert resp.status == 200
        data = await resp.json()
        assert data["settings"]["notify_start"] is False
        assert self.dummy_app.global_settings["notify_start"] is False

    @unittest_run_loop
    async def test_update_settings_invalid(self):
        resp = await self.client.post("/api/settings", data="invalid json")
        assert resp.status == 400

    @unittest_run_loop
    async def test_auth_rejection(self):
        resp = await self.client.get("/api/settings", headers={"X-Forwarded-For": "1.2.3.4"})
        assert resp.status == 401
