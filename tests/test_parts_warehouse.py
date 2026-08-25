"""
Unit and integration tests for Parts Warehouse management API endpoints (Simplified 3D parts structure & Print trigger).
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from aiohttp.test_utils import AioHTTPTestCase

from app import PrinterBotApp
from services.http_server import create_http_app
from storage.manager import StorageManager


class TestPartsWarehouseAPI(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)

        import config
        self.orig_storage_dir = config.STORAGE_DIR
        config.STORAGE_DIR = self.temp_dir

        self.app_obj = PrinterBotApp()
        self.app_obj.storage = StorageManager(self.temp_dir)
        self.app_obj.storage.parts_file = self.temp_dir / "parts.json"

        # Mock printer for print testing
        mock_p = MagicMock()
        mock_p.id = "p1"
        mock_p.name = "Bambu Lab P1S"
        mock_p.gcode_state = "IDLE"
        mock_p.start_print_job_async = AsyncMock(return_value=(True, "Print started"))
        self.app_obj.printers = {"p1": mock_p}

        return create_http_app(self.app_obj)

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "temp_dir_obj"):
            self.temp_dir_obj.cleanup()

    async def test_parts_api_crud_flow(self):
        # 1. GET /api/parts (empty)
        resp = await self.client.get("/api/parts")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data, {})

        # 2. POST /api/parts (Create part)
        part_payload = {
            "name": "Кронштейн P1S",
            "image": "AgACAgIAAxk...",
            "count": 10,
            "three_mf": "model_test.3mf"
        }
        resp = await self.client.post("/api/parts", json=part_payload)
        self.assertEqual(resp.status, 200)
        res_data = await resp.json()
        self.assertEqual(res_data["status"], "ok")
        part = res_data["part"]
        part_id = part["id"]

        self.assertEqual(part["name"], "Кронштейн P1S")
        self.assertEqual(part["count"], 10)
        self.assertEqual(part["three_mf"], "model_test.3mf")

        # Create dummy file on storage to test print execution
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "model_test.3mf").write_bytes(b"PK\x03\x04Dummy 3MF Content")

        # 3. POST /api/parts/{part_id}/print/{printer_id}
        print_resp = await self.client.post(f"/api/parts/{part_id}/print/p1")
        self.assertEqual(print_resp.status, 200)
        print_data = await print_resp.json()
        self.assertEqual(print_data["status"], "ok")

        # 4. DELETE /api/parts/{id}
        resp = await self.client.delete(f"/api/parts/{part_id}")
        self.assertEqual(resp.status, 200)

        resp = await self.client.get("/api/parts")
        self.assertEqual(resp.status, 200)
        all_parts = await resp.json()
        self.assertNotIn(part_id, all_parts)
