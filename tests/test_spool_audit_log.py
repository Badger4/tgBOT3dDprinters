"""
Unit tests for Warehouse Spool Movement Audit Log storage & REST API endpoints.
"""

import tempfile
from pathlib import Path
from aiohttp.test_utils import AioHTTPTestCase

from app import PrinterBotApp
from services.http_server import create_http_app
from storage.manager import StorageManager


class TestSpoolAuditLog(AioHTTPTestCase):
    async def get_application(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)

        import config
        config.STORAGE_DIR = self.temp_dir

        self.app_obj = PrinterBotApp()
        self.app_obj.storage = StorageManager(self.temp_dir)
        self.app_obj.storage.spools_file = self.temp_dir / "spools.json"
        self.app_obj.storage.movements_file = self.temp_dir / "warehouse_movements.json"

        from services.http.auth import create_web_session
        self.auth_token = create_web_session()
        self.headers = {"X-Session-Token": self.auth_token}

        return create_http_app(self.app_obj)

    def tearDown(self):
        super().tearDown()
        if hasattr(self, "temp_dir_obj"):
            self.temp_dir_obj.cleanup()

    async def test_spool_movement_storage_and_api(self):
        # 1. Add initial spool (1000g)
        spool_data = {
            "id": "spool_audit_1",
            "name": "Audit PLA Red",
            "type": "PLA",
            "remaining_grams": 1000.0,
            "quantity": 1
        }
        res1 = await self.client.post("/api/spools", json=spool_data, headers=self.headers)
        self.assertEqual(res1.status, 200)

        # 2. Update spool weight (Refill to 1200g) -> triggers "refill" audit entry
        spool_data["remaining_grams"] = 1200.0
        res2 = await self.client.post("/api/spools", json=spool_data, headers=self.headers)
        self.assertEqual(res2.status, 200)

        # 3. GET /api/spools/movements -> should contain initial_stock and refill (2 entries)
        res_mov = await self.client.get("/api/spools/movements", headers=self.headers)
        self.assertEqual(res_mov.status, 200)
        mov_list = await res_mov.json()
        self.assertEqual(len(mov_list), 2)
        self.assertEqual(mov_list[0]["spool_id"], "spool_audit_1")
        self.assertEqual(mov_list[0]["action"], "refill")
        self.assertEqual(mov_list[0]["weight_change_g"], 200.0)

        # 4. Manual weight edit (Deduct to 1100g) -> triggers "manual_edit" audit entry
        spool_data["remaining_grams"] = 1100.0
        res3 = await self.client.post("/api/spools", json=spool_data, headers=self.headers)
        self.assertEqual(res3.status, 200)

        res_mov2 = await self.client.get("/api/spools/movements?spool_id=spool_audit_1", headers=self.headers)
        self.assertEqual(res_mov2.status, 200)
        mov_list2 = await res_mov2.json()
        self.assertEqual(len(mov_list2), 3)

        # 5. Export movements PDF
        res_pdf = await self.client.get("/api/spools/movements/export_csv", headers=self.headers)
        self.assertEqual(res_pdf.status, 200)
        pdf_bytes = await res_pdf.read()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # 6. Delete spool -> triggers "write_off" audit entry
        res_del = await self.client.delete("/api/spools/spool_audit_1", headers=self.headers)
        self.assertEqual(res_del.status, 200)

        res_mov3 = await self.client.get("/api/spools/movements", headers=self.headers)
        mov_list3 = await res_mov3.json()
        self.assertEqual(len(mov_list3), 4)
        self.assertEqual(mov_list3[0]["action"], "write_off")

    async def test_mount_and_unmount_spool_api(self):
        # Create dummy printer
        mock_p = type("Printer", (), {
            "id": "p_test_1",
            "name": "Bambu A1",
            "set_slot_grams": lambda self, g, slot_id="0": None
        })()
        self.app_obj.printers["p_test_1"] = mock_p
        self.app_obj.save_printers_config = lambda: None

        spool_data = {
            "id": "spool_mount_1",
            "name": "Mount Test Spool",
            "type": "PETG",
            "remaining_grams": 800.0
        }
        await self.client.post("/api/spools", json=spool_data, headers=self.headers)

        # Mount spool
        res_mount = await self.client.post(
            "/api/spools/spool_mount_1/mount",
            json={"printer_id": "p_test_1", "slot_key": "0"},
            headers=self.headers
        )
        self.assertEqual(res_mount.status, 200)
        data_mount = await res_mount.json()
        self.assertEqual(data_mount["spool"]["assigned_printer_id"], "p_test_1")
        self.assertEqual(data_mount["spool"]["assigned_slot_key"], "0")

        # Unmount spool
        res_unmount = await self.client.post("/api/spools/spool_mount_1/unmount", json={}, headers=self.headers)
        self.assertEqual(res_unmount.status, 200)
        data_unmount = await res_unmount.json()
        self.assertIsNone(data_unmount["spool"]["assigned_printer_id"])
        self.assertIsNone(data_unmount["spool"]["assigned_slot_key"])

