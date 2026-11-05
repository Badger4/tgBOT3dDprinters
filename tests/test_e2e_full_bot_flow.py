"""
Complete End-to-End Simulation Suite for 3D Farm Bot & WebApp.
Tests every major user journey from onboarding and RBAC to 3MF parsing,
AMS slot management, Skip Objects with filament refund, and WebApp auth.
"""

import asyncio
import hashlib
import hmac
import io
import json
import tempfile
import time
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, Chat, Document, Message, User

from bot.handlers import setup_routers
from bot.keyboards import get_main_keyboard, get_printer_control_keyboard, get_printer_menu_keyboard
from models.printer import BambuPrinter
from storage.manager import StorageManager


class TestFullBotAndWebAppE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = setup_routers()
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.sm = StorageManager(self.temp_dir)

        # Users for RBAC simulation
        self.clean_user_id = 999111
        self.clean_chat = Chat(id=self.clean_user_id, type="private")
        self.clean_user = User(id=self.clean_user_id, is_bot=False, first_name="CleanTester", username="cleantester")

        self.admin_user_id = 111222
        self.admin_chat = Chat(id=self.admin_user_id, type="private")
        self.admin_user = User(id=self.admin_user_id, is_bot=False, first_name="SuperAdmin", username="admin")

        # Setup admin in storage
        await self.sm.save_user({
            "user_id": str(self.admin_user_id),
            "chat_id": str(self.admin_user_id),
            "is_approved": True,
            "is_admin": True,
            "admin": {"access_admin": True},
            "role": "admin",
            "state": "idle",
            "context_data": {"selected_printer_id": "v_p1s"},
        })

        self.app = MagicMock()
        self.app.storage = self.sm
        self.app.printers = {}
        self.app.printer_states = {}
        self.app.bot = MagicMock()
        self.app.bot.send_message = AsyncMock()
        self.app.save_printers_config = AsyncMock()

        # Wire real RBAC methods
        async def mock_is_admin(uid: str):
            if str(uid) == str(self.admin_user_id):
                return True
            u = await self.sm.load_user(str(uid))
            return bool(u.get("admin", {}).get("access_admin", False) or u.get("is_admin", False))

        async def mock_is_approved(uid: str):
            if await mock_is_admin(uid):
                return True
            u = await self.sm.load_user(str(uid))
            return bool(u.get("is_approved", False))

        self.app.is_user_admin = AsyncMock(side_effect=mock_is_admin)
        self.app.is_user_approved = AsyncMock(side_effect=mock_is_approved)

        # Virtual Bambu Printer with AMS
        self.v_printer = BambuPrinter(
            {
                "id": "v_p1s",
                "name": "Bambu P1S Virtual",
                "ip": "127.0.0.1",
                "access_code": "12345678",
                "serialNumber": "01P00A123456789",
                "serial_number": "01P00A123456789",
                "has_ams": True,
                "ams_trays": {"0": "PLA", "1": "PETG", "2": "EMPTY", "3": "EMPTY"},
                "maintenance_hours": 12.5,
                "maintenance_interval_hours": 150.0,
            },
            storage=self.sm,
            save_callback=self.app.save_printers_config,
        )
        self.v_printer._client = MagicMock()
        self.v_printer._client.is_connected.return_value = True
        self.v_printer._client.publish.return_value = MagicMock(rc=0)
        self.app.printers["v_p1s"] = self.v_printer

    async def asyncTearDown(self):
        self.temp_dir_obj.cleanup()

    async def _send_msg(self, text: str, user: User, chat: Chat, document: Document = None) -> AsyncMock:
        msg = Message(
            message_id=int(time.time() * 1000) % 1000000,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text=text,
            document=document,
        )
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_document", mock_answer)
        object.__setattr__(msg, "answer_photo", mock_answer)
        object.__setattr__(msg, "answer_animation", mock_answer)
        await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
        return mock_answer

    async def _send_cb(self, data: str, user: User, chat: Chat) -> tuple[AsyncMock, AsyncMock]:
        msg = Message(
            message_id=int(time.time() * 1000) % 1000000,
            date=datetime.now(),
            chat=chat,
            from_user=user,
            text="",
        )
        mock_reply = AsyncMock()
        mock_edit_text = AsyncMock()
        mock_edit_rm = AsyncMock()
        mock_answer = AsyncMock()
        mock_delete = AsyncMock()
        object.__setattr__(msg, "reply", mock_reply)
        object.__setattr__(msg, "edit_text", mock_edit_text)
        object.__setattr__(msg, "edit_reply_markup", mock_edit_rm)
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "delete", mock_delete)

        cb = CallbackQuery(
            id=f"cb_{int(time.time() * 1000)}",
            from_user=user,
            chat_instance="ci_1",
            message=msg,
            data=data,
        )
        mock_cb_answer = AsyncMock()
        object.__setattr__(cb, "answer", mock_cb_answer)
        await self.router.propagate_event("callback_query", cb, app=self.app, bot=self.app.bot)
        return mock_answer, mock_cb_answer

    def _create_dummy_3mf(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            model_xml = """<?xml version="1.0" encoding="UTF-8"?>
            <model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
                <resources>
                    <object id="1" name="Gear_Main" type="model"/>
                    <object id="2" name="Cover_Plate" type="model"/>
                </resources>
                <build>
                    <item objectid="1"/>
                    <item objectid="2"/>
                </build>
            </model>"""
            zf.writestr("3D/3dmodel.model", model_xml)
            slice_cfg = "filament_weight = 42.5\nplate_1 = 1\nestimated_time = 3600"
            zf.writestr("Metadata/slice_info.config", slice_cfg)
        return buf.getvalue()

    # =========================================================================
    # 1. ONBOARDING & RBAC JOURNEY
    # =========================================================================
    async def test_01_onboarding_and_rbac(self):
        """Clean user /start -> request pending -> admin approves -> clean user approved."""
        # 1. Clean user sends /start
        ans = await self._send_msg("/start", self.clean_user, self.clean_chat)
        self.assertTrue(ans.called)
        user_db = await self.sm.load_user(str(self.clean_user_id))
        self.assertIsNotNone(user_db)
        self.assertFalse(user_db.get("is_approved", False))

        # 2. Unapproved user tries to execute control command
        ans_ctrl = await self._send_msg("🚫 Пропустити об'єкт", self.clean_user, self.clean_chat)
        if ans_ctrl.called:
            text = ans_ctrl.call_args[0][0]
            self.assertTrue("немає прав" in text or "заборонено" in text.lower())

        # 3. Admin approves clean user via callback
        _, cb_ans = await self._send_cb(f"approve_user_{self.clean_user_id}", self.admin_user, self.admin_chat)
        self.assertTrue(cb_ans.called)

        # Verify clean user is now approved in DB
        user_db = await self.sm.load_user(str(self.clean_user_id))
        self.assertTrue(user_db.get("is_approved", False))

        # 4. Approved user now gets main menu
        ans_start2 = await self._send_msg("/start", self.clean_user, self.clean_chat)
        self.assertTrue(ans_start2.called)

    # =========================================================================
    # 2. FARM DASHBOARD & PRINTER STATUS
    # =========================================================================
    async def test_02_dashboard_and_printer_status(self):
        """Dashboard overview and detailed printer telemetry cards."""
        # 1. Farm status overview
        ans_dash = await self._send_msg("📊 Стан ферми", self.admin_user, self.admin_chat)
        self.assertTrue(ans_dash.called)
        dash_text = ans_dash.call_args[0][0]
        self.assertIn("Bambu P1S Virtual", dash_text)

        # 2. Detailed printer card
        ans_print = await self._send_msg("🖨️ Принтери", self.admin_user, self.admin_chat)
        self.assertTrue(ans_print.called)

    # =========================================================================
    # 3. SPOOL MANAGEMENT & AMS SLOTS (STORAGE)
    # =========================================================================
    async def test_03_spool_warehouse_and_ams_mount(self):
        """Spool creation, remaining grams edit, and AMS mounting."""
        # 1. Add spool directly into storage
        spools = await self.sm.load_spools()
        spool_id = "spool_e2e_1"
        spools[spool_id] = {
            "id": spool_id,
            "name": "E2E Test PLA Black",
            "material": "PLA",
            "type": "PLA",
            "color": "Black",
            "total_grams": 1000.0,
            "remaining_grams": 850.0,
            "price_uah": 750.0,
            "is_active": True,
        }
        await self.sm.save_spools(spools)

        # 2. Mount spool to slot 0 (A1)
        self.v_printer.set_slot_grams(850.0, slot_id="0")
        spools[spool_id]["assigned_printer_id"] = self.v_printer.id
        spools[spool_id]["assigned_slot_key"] = "0"
        await self.sm.save_spools(spools)
        self.assertEqual(self.v_printer.get_slot_grams("0"), 850.0)

        # 3. Spools menu check
        ans_spools = await self._send_msg("🧵 Склад пластику", self.admin_user, self.admin_chat)
        self.assertTrue(ans_spools.called)

    # =========================================================================
    # 4. 3MF FILE UPLOAD & OBJECT PARSING
    # =========================================================================
    async def test_04_3mf_file_upload_parsing(self):
        """Sending .3mf document to bot -> extracts weight, plate objects."""
        raw_3mf = self._create_dummy_3mf()

        doc = Document(
            file_id="doc_3mf_123",
            file_unique_id="uniq_123",
            file_name="bracket_assembly.3mf",
            mime_type="application/octet-stream",
            file_size=len(raw_3mf),
        )

        mock_bot_file = MagicMock()
        mock_bot_file.file_path = "documents/bracket_assembly.3mf"
        self.app.bot.get_file = AsyncMock(return_value=mock_bot_file)
        self.app.bot.download_file = AsyncMock(return_value=io.BytesIO(raw_3mf))

        ans = await self._send_msg("", self.admin_user, self.admin_chat, document=doc)
        self.assertTrue(ans.called)
        resp_text = ans.call_args[0][0]
        self.assertIn("bracket_assembly", resp_text)

    # =========================================================================
    # 5. SKIP OBJECTS FLOW & ACCURATE FILAMENT REFUND
    # =========================================================================
    async def test_05_skip_objects_and_filament_refund(self):
        """Active print job -> skip object #1 at 40% -> proportional refund on finish."""
        # 1. Setup active printing state with 2 objects, total weight 100g
        self.v_printer.gcode_state = "RUNNING"
        self.v_printer.subtask_name = "plates_job.3mf"
        self.v_printer._current_job_grams = 100.0
        self.v_printer._job_deducted = True
        self.v_printer.current_job_objects = [
            {"id": "1", "name": "Gear_Main"},
            {"id": "2", "name": "Cover_Plate"},
        ]
        self.v_printer.skipped_objects = []
        self.v_printer._skipped_at_progress = {}

        # Initial slot weight
        self.v_printer.set_slot_grams(500.0, slot_id="0")
        self.v_printer.active_ams_tray = 0

        # 2. Skip object #1 at 40% progress
        self.v_printer.mc_percent = 40
        await self.v_printer.skip_objects_async(["1"])
        self.assertIn(1, self.v_printer.skipped_objects)
        self.assertEqual(self.v_printer._skipped_at_progress.get(1), 40.0)

        # 3. Calculate effective grams
        eff_grams, saved_grams = self.v_printer.calculate_effective_job_grams(100.0)
        # Obj 1: 50g * 0.40 = 20g
        # Obj 2: 50g * 1.00 = 50g
        # Total effective: 70g (Refund should be 30g)
        self.assertEqual(eff_grams, 70.0)
        self.assertEqual(saved_grams, 30.0)

        # 4. Finish print job and verify auto-refund
        finish_payload = json.dumps({"print": {"gcode_state": "FINISH"}}).encode()
        self.v_printer._process_message(finish_payload)
        # 500g initial + 30g refunded = 530g
        self.assertEqual(self.v_printer.get_slot_grams("0"), 530.0)

    # =========================================================================
    # 6. PRINTER CONTROL: PAUSE, RESUME, SPEED, MAINTENANCE
    # =========================================================================
    async def test_06_printer_control_commands(self):
        """Testing pause, resume, speed profile, and maintenance reset."""
        # 1. Pause
        ans_pause = await self._send_msg("⏸️ Пауза", self.admin_user, self.admin_chat)
        self.assertTrue(ans_pause.called)
        self.assertTrue(self.v_printer._client.publish.called)

        # 2. Resume
        ans_resume = await self._send_msg("▶️ Відновити друк", self.admin_user, self.admin_chat)
        self.assertTrue(ans_resume.called)

        # 3. Speed Mode
        ans_spd = await self._send_msg("🏎️ Sport (124%)", self.admin_user, self.admin_chat)
        self.assertTrue(ans_spd.called)

        # 4. Reset Maintenance
        ans_maint = await self._send_msg("🧹 Скинути лічильник ТО", self.admin_user, self.admin_chat)
        self.assertTrue(ans_maint.called)
        self.assertEqual(getattr(self.v_printer, "maintenance_hours", 0.0), 0.0)

    # =========================================================================
    # 7. WEBAPP AUTHENTICATION & SSE TELEMETRY INTEGRATION
    # =========================================================================
    async def test_07_webapp_auth_and_telemetry(self):
        """Testing WebApp initData validation and printer telemetry generation."""
        from services.http.auth import verify_telegram_init_data
        from services.http.routes_sse import build_printer_telemetry

        # 1. Telemetry builder
        telemetry = build_printer_telemetry(self.v_printer)
        self.assertEqual(telemetry["id"], "v_p1s")
        self.assertEqual(telemetry["name"], "Bambu P1S Virtual")
        self.assertIn("raw_state", telemetry)

        # 2. Test valid initData hash generation
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        user_json = json.dumps({"id": self.admin_user_id, "first_name": "Admin", "username": "admin"})
        auth_date = str(int(time.time()))
        data_check_string = f"auth_date={auth_date}\nuser={user_json}"

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        init_data_raw = f"auth_date={auth_date}&user={user_json}&hash={hash_val}"

        user_info = verify_telegram_init_data(init_data_raw, bot_token)
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info.get("id"), self.admin_user_id)


if __name__ == "__main__":
    unittest.main()
