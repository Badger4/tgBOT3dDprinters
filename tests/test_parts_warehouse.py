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

    async def test_parts_download_3mf(self):
        # Create part with 3MF file
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "file1.3mf").write_bytes(b"PK\x03\x04Test3MFData")

        part_payload = {
            "name": "Test Part",
            "count": 5,
            "three_mf": "file1.3mf"
        }
        resp = await self.client.post("/api/parts", json=part_payload)
        res_data = await resp.json()
        part_id = res_data["part"]["id"]

        # Download existing 3MF
        dl_resp = await self.client.get(f"/api/parts/{part_id}/download_3mf")
        self.assertEqual(dl_resp.status, 200)
        body = await dl_resp.read()
        self.assertEqual(body, b"PK\x03\x04Test3MFData")

        # Download non-existent part
        dl_404 = await self.client.get("/api/parts/non_existent_part/download_3mf")
        self.assertEqual(dl_404.status, 404)

        # Download part with missing file
        no_file_payload = {"name": "No File Part", "count": 1}
        resp_nf = await self.client.post("/api/parts", json=no_file_payload)
        part_nf_id = (await resp_nf.json())["part"]["id"]
        dl_nf = await self.client.get(f"/api/parts/{part_nf_id}/download_3mf")
        self.assertEqual(dl_nf.status, 404)

    async def test_parts_export_csv(self):
        part_payload = {"name": "Part A", "count": 2}
        await self.client.post("/api/parts", json=part_payload)

        resp = await self.client.get("/api/parts/export_csv")
        self.assertEqual(resp.status, 200)
        self.assertIn("text/csv", resp.headers.get("Content-Type", ""))

    async def test_parts_print_compatibility_and_errors(self):
        part_payload = {
            "name": "PLA Model",
            "count": 1,
            "three_mf": "model_b.3mf",
            "printer_model": "Bambu Lab P1S",
            "filament_type": "PLA"
        }
        resp = await self.client.post("/api/parts", json=part_payload)
        res_data = await resp.json()
        part_id = res_data["part"]["id"]

        # Print on missing printer
        p_err1 = await self.client.post(f"/api/parts/{part_id}/print/non_existent_printer")
        self.assertEqual(p_err1.status, 404)

        # Print on missing part
        p_err_part = await self.client.post("/api/parts/non_existent_part/print/p1")
        self.assertEqual(p_err_part.status, 404)

        # Print without 3MF file on disk
        p_err2 = await self.client.post(f"/api/parts/{part_id}/print/p1")
        self.assertEqual(p_err2.status, 404)

        # Create file on disk
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "model_b.3mf").write_bytes(b"PK\x03\x04DummyContent")

        # Test incompatible print
        from unittest.mock import patch
        with patch("services.gcode_parser.check_compatibility", return_value={"compatible": False, "reason": "Incompatible printer model"}):
            p_inc = await self.client.post(f"/api/parts/{part_id}/print/p1")
            self.assertEqual(p_inc.status, 400)

        # Test failed print job start
        self.app_obj.printers["p1"].start_print_job_async = AsyncMock(return_value=(False, "FTPS Connection error"))
        p_failed = await self.client.post(f"/api/parts/{part_id}/print/p1")
        self.assertEqual(p_failed.status, 500)

    async def test_parts_metadata_parsing_on_get_and_save(self):
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "meta_model.3mf").write_bytes(b"PK\x03\x04Meta3MF")

        from unittest.mock import patch
        mock_meta = {
            "printer_model": "Bambu Lab A1 mini",
            "filament_type": "PETG",
            "weight_g": 35.5,
            "time_mins": 42,
        }

        with patch("services.gcode_parser.parse_3mf_file", return_value=mock_meta):
            part_payload = {
                "name": "Auto Meta Part",
                "count": 1,
                "three_mf": "meta_model.3mf"
            }
            resp = await self.client.post("/api/parts", json=part_payload)
            res_data = await resp.json()
            part = res_data["part"]

            self.assertEqual(part["printer_model"], "Bambu Lab A1 mini")
            self.assertEqual(part["filament_type"], "PETG")
            self.assertEqual(part["weight_g"], 35.5)

            # Test GET /api/parts triggering parse
            get_resp = await self.client.get("/api/parts")
            self.assertEqual(get_resp.status, 200)

    async def test_parts_get_auto_parse_existing_3mf(self):
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "auto_parse.3mf").write_bytes(b"PK\x03\x04Dummy")

        # Save part without weight_g / time_mins
        parts = {
            "p_autoparse": {
                "id": "p_autoparse",
                "name": "Auto Parse Part",
                "three_mf": "auto_parse.3mf",
                "printer_model": "Unknown",
            }
        }
        await self.app_obj.storage.save_json(self.app_obj.storage.parts_file, parts)

        mock_meta = {
            "printer_model": "Bambu Lab P1P",
            "filament_type": "PETG",
            "weight_g": 50.0,
            "time_mins": 60,
        }

        from unittest.mock import patch
        with patch("services.gcode_parser.parse_3mf_file", return_value=mock_meta):
            resp = await self.client.get("/api/parts")
            self.assertEqual(resp.status, 200)
            data = await resp.json()
            p = data["p_autoparse"]
            self.assertEqual(p["printer_model"], "Bambu Lab P1P")
            self.assertEqual(p["filament_type"], "PETG")

