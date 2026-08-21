"""
Unit tests for editing printer attributes (Name, IP, Serial Number, Access Code) in Telegram bot.
"""

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Chat, Message, User

from bot.handlers import setup_routers
from models.printer import BambuPrinter
from storage.manager import StorageManager


class TestEditPrinterBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = setup_routers()
        self.sm = StorageManager(Path("./test_edit_p_storage"))
        self.app = MagicMock()
        self.app.storage = self.sm
        self.app.printers = {}
        self.app.is_user_approved = AsyncMock(return_value=True)
        self.app.is_user_admin = AsyncMock(return_value=True)
        self.app.save_printers_config = AsyncMock()

        self.chat = Chat(id=999, type="private")
        self.user_obj = User(id=999, is_bot=False, first_name="TestUser")

        # Create dummy printer
        p_data = {
            "id": "p_test_1",
            "name": "Test Printer A1",
            "ip": "192.168.1.10",
            "serialNumber": "SN123456789",
            "accessCode": "12345678",
            "filament_grams": 800.0,
        }
        self.printer = BambuPrinter(p_data, self.sm, save_callback=self.app.save_printers_config)
        self.app.printers["p_test_1"] = self.printer

        # Setup user in storage
        await self.sm.save_user(
            {
                "user_id": "999",
                "chat_id": "999",
                "state": "printer_menu",
                "language": "uk",
                "context_data": {"selected_printer_id": "p_test_1"},
            }
        )

    async def asyncTearDown(self):
        import shutil

        shutil.rmtree("./test_edit_p_storage", ignore_errors=True)

    async def _send_msg(self, text: str) -> AsyncMock:
        msg = Message(message_id=202, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text=text)
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
        return mock_answer

    async def test_edit_printer_name(self):
        # 1. Click "✏️ Редагувати принтер"
        ans = await self._send_msg("✏️ Редагувати принтер")
        self.assertTrue(ans.called)
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "edit_printer_menu")

        # 2. Click "✏️ Назва принтера"
        ans = await self._send_msg("✏️ Назва принтера")
        self.assertTrue(ans.called)
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "edit_p_name")

        # 3. Enter new name
        ans = await self._send_msg("Bambu Lab Super A1")
        self.assertTrue(ans.called)
        self.assertEqual(self.printer.name, "Bambu Lab Super A1")
        self.app.save_printers_config.assert_called()
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "printer_menu")

    async def test_edit_printer_ip(self):
        await self._send_msg("✏️ Редагувати принтер")
        await self._send_msg("🌐 IP адреса")
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "edit_p_ip")

        await self._send_msg("192.168.1.99")
        self.assertEqual(self.printer.ip, "192.168.1.99")
        self.app.save_printers_config.assert_called()

    async def test_edit_printer_serial_number(self):
        await self._send_msg("✏️ Редагувати принтер")
        await self._send_msg("🔢 Серійний номер")
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "edit_p_sn")

        await self._send_msg("SN999888777")
        self.assertEqual(self.printer.serial_number, "SN999888777")
        self.app.save_printers_config.assert_called()

    async def test_edit_printer_access_code(self):
        await self._send_msg("✏️ Редагувати принтер")
        await self._send_msg("🔑 Access Code")
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "edit_p_code")

        await self._send_msg("87654321")
        self.assertEqual(self.printer.access_code, "87654321")
        self.app.save_printers_config.assert_called()

    async def test_edit_printer_cancel(self):
        await self._send_msg("✏️ Редагувати принтер")
        ans = await self._send_msg("⬅️ Назад")
        self.assertTrue(ans.called)
        u_data = await self.sm.load_user("999")
        self.assertEqual(u_data.get("state"), "printer_menu")


if __name__ == "__main__":
    unittest.main()
