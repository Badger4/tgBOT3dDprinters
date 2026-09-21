"""
Unit tests for filament mounting navigation:
- Mounting from warehouse returns to warehouse menu
- Clicking Back after warehouse mount returns to main menu, not to printer
- Step-back navigation during warehouse mounting
- Mounting from printer returns to printer filament menu
"""

import asyncio
from datetime import datetime
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock

from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, User as TgUser
from pathlib import Path

from bot.handlers import setup_routers
from models.printer import BambuPrinter
from storage.manager import StorageManager
from bot.keyboards import get_filament_menu_keyboard, get_single_printer_filament_keyboard


class DummyApp:
    def __init__(self, data_dir: str):
        self.storage = StorageManager(Path(data_dir))
        self.data_dir = data_dir
        self.printers: dict[str, BambuPrinter] = {}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, chat_id: str) -> bool:
        return True

    async def is_user_admin(self, chat_id: str) -> bool:
        return True


class TestFilamentMountNavigation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.app = DummyApp(self.temp_dir)
        self.bot = AsyncMock()
        self.app.bot = self.bot
        self.router = setup_routers()

        # Seed test user
        await self.app.storage.save_user({
            "user_id": "999",
            "chat_id": "999",
            "username": "tester",
            "state": "idle",
            "language": "uk",
            "context_data": {},
        })

        # Printer with AMS
        self.p1 = BambuPrinter(
            {
                "id": "p1",
                "name": "Bambu Lab P1S",
                "ip": "192.168.1.10",
                "accessCode": "12345678",
                "serialNumber": "01P1S000000001",
                "printer_model": "P1S",
                "ams_enabled": True,
            },
            storage=self.app.storage,
        )
        self.p1.ams_status = 1
        self.p1.ams_slots = {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.0, "254": 0.0}
        self.p1.ams_trays_info = {
            "0": {"empty": True, "type": ""},
            "1": {"empty": True, "type": ""},
            "2": {"empty": True, "type": ""},
            "3": {"empty": True, "type": ""},
        }
        self.app.printers["p1"] = self.p1

        # Spool in warehouse
        await self.app.storage.save_spools({
            "spool_1": {
                "id": "spool_1",
                "name": "Bambu PLA Basic Black",
                "type": "PLA",
                "color": "#000000",
                "color_name": "Чорний",
                "remaining_grams": 1000.0,
                "price_per_kg": 850.0,
                "quantity": 1,
                "assigned_printer_id": None,
                "assigned_slot_key": None,
            }
        })

    async def asyncTearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def _send(self, text: str) -> MagicMock:
        tg_user = TgUser(id=999, is_bot=False, first_name="Tester", username="tester")
        chat = Chat(id=999, type="private")
        msg = Message(
            message_id=1,
            date=datetime.now(),
            chat=chat,
            from_user=tg_user,
            text=text,
        )
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_photo", mock_answer)

        await self.router.propagate_event(
            update_type="message",
            event=msg,
            app=self.app,
            bot=self.bot,
        )
        return mock_answer

    async def test_warehouse_mount_flow_and_back_returns_to_main_menu(self):
        """User mounts spool from warehouse, then presses Back: must return to Main Menu, NOT printer menu."""
        # 1. Open Warehouse
        await self._send("📦 Склад")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")
        self.assertNotIn("selected_printer_id", u.get("context_data", {}))

        # 2. Click Mount to printer
        ans_start = await self._send("🔗 Встановити на принтер")
        self.assertTrue(ans_start.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_mount")
        self.assertEqual(u.get("context_data", {}).get("mount_source"), "warehouse")

        # 3. Select spool
        ans_spool = await self._send("🧵 Bambu PLA Basic Black (1000.0g)")
        self.assertTrue(ans_spool.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_printer_for_mount")

        # 4. Select printer
        ans_p = await self._send("🖨️ Bambu Lab P1S")
        self.assertTrue(ans_p.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_mount")

        # 5. Select AMS slot
        ans_slot = await self._send("📍 Слот A1 (Slot 1)")
        self.assertTrue(ans_slot.called)
        u = await self.app.storage.load_user("999")

        # Verify state is returned to idle and selected_printer_id is removed
        self.assertEqual(u["state"], "idle")
        self.assertIsNone(u.get("context_data", {}).get("selected_printer_id"))
        self.assertIsNone(u.get("context_data", {}).get("mount_source"))

        # Verify warehouse menu reply_markup was sent
        wh_reply = ans_slot.call_args_list[0]
        self.assertIn("reply_markup", wh_reply[1])
        kb = wh_reply[1]["reply_markup"]
        all_btn_texts = [b.text for row in kb.keyboard for b in row]
        self.assertIn("➕ Додати", all_btn_texts)
        self.assertIn("🔗 Встановити на принтер", all_btn_texts)

        # 6. Now user clicks Back: must return to Main Menu, NOT printer menu!
        ans_back = await self._send("⬅️ Назад")
        self.assertTrue(ans_back.called)
        back_text = " ".join(str(call[0][0]) for call in ans_back.call_args_list)
        self.assertIn("Головне меню", back_text)
        self.assertNotIn("Повертаю у меню Bambu Lab P1S", back_text)

    async def test_step_back_during_warehouse_mount(self):
        """Test step-back navigation during spool mounting from warehouse."""
        await self._send("📦 Склад")
        await self._send("🔗 Встановити на принтер")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_mount")

        # Select spool
        await self._send("🧵 Bambu PLA Basic Black (1000.0g)")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_printer_for_mount")

        # Select printer
        await self._send("🖨️ Bambu Lab P1S")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_mount")

        # Step back from slot selection -> goes back to printer selection
        ans_back1 = await self._send("⬅️ Назад")
        self.assertTrue(ans_back1.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_printer_for_mount")

        # Step back from printer selection -> goes back to spool selection
        ans_back2 = await self._send("⬅️ Назад")
        self.assertTrue(ans_back2.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_mount")

        # Step back from spool selection -> cancels back to warehouse
        ans_back3 = await self._send("⬅️ Назад")
        self.assertTrue(ans_back3.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")

    async def test_printer_mount_flow_and_back_returns_to_printer(self):
        """Mounting initiated from printer menu stays in printer context on Back."""
        # 1. User is in printer menu
        await self.app.storage.save_user({
            "user_id": "999",
            "chat_id": "999",
            "username": "tester",
            "state": "printer_menu",
            "language": "uk",
            "context_data": {"selected_printer_id": "p1"},
        })

        # 2. Click Mount Spool button from printer filament menu
        ans_mount = await self._send("🔗 Поставити котушку")
        self.assertTrue(ans_mount.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_mount")
        self.assertEqual(u.get("context_data", {}).get("mount_source"), "printer")

        # 3. Select spool -> since printer is known, directly asks for slot!
        ans_spool = await self._send("🧵 Bambu PLA Basic Black (1000.0g)")
        self.assertTrue(ans_spool.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_mount")

        # 4. Select slot -> mounts to printer
        ans_slot = await self._send("📍 Слот A1 (Slot 1)")
        self.assertTrue(ans_slot.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "printer_menu")
        self.assertEqual(u.get("context_data", {}).get("selected_printer_id"), "p1")

        # 5. Pressing Back returns to printer menu
        ans_back = await self._send("⬅️ Назад")
        self.assertTrue(ans_back.called)
        back_text = " ".join(str(call[0][0]) for call in ans_back.call_args_list)
        self.assertIn("Bambu Lab P1S", back_text)

    async def test_warehouse_spool_quantity_display(self):
        """Test that warehouse displays total quantity across spools with quantity > 1."""
        await self.app.storage.save_spools({
            "spool_1": {
                "id": "spool_1",
                "name": "Bambu PLA Basic Black",
                "type": "PLA",
                "color": "#000000",
                "color_name": "Чорний",
                "remaining_grams": 1000.0,
                "price_per_kg": 850.0,
                "quantity": 20,
                "assigned_printer_id": None,
                "assigned_slot_key": None,
            }
        })
        ans = await self._send("📦 Склад")
        self.assertTrue(ans.called)
        call_text = ans.call_args[0][0]
        self.assertIn("20 шт. (1 поз.)", call_text)
        self.assertIn("[<b>20 шт.</b>]", call_text)