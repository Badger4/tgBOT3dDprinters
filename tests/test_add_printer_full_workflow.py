import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Chat, Message

from bot.handlers.printers.add import handle_add_printer_start, handle_printer_states
from bot.keyboards import get_printers_keyboard
from models.printer import BambuPrinter
from services.http.routes_printers import build_printer_telemetry


class TestAddPrinterWorkflow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = MagicMock()
        self.app.printers = {}
        self.app.storage = MagicMock()
        self.app.save_printers_config = AsyncMock()
        self.app.is_user_approved = AsyncMock(return_value=True)

        self.user_data = {
            "state": "idle",
            "language": "uk",
            "context_data": {},
        }
        self.app.storage.load_user = AsyncMock(return_value=self.user_data)
        self.app.storage.save_user = AsyncMock()

    def _create_message(self, text: str) -> Message:
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = text
        msg.answer = AsyncMock()
        return msg

    @patch("models.printer.mqtt.Client")
    async def test_full_add_printer_success(self, mock_mqtt):
        # 1. Start wizard
        msg_start = self._create_message("➕ Додати принтер")
        await handle_add_printer_start(msg_start, self.app)
        self.assertEqual(self.user_data["state"], "add_p_name")
        self.assertIn("new_printer", self.user_data["context_data"])

        # 2. Enter name
        msg_name = self._create_message("Bambu Lab A1 mini 2")
        handled = await handle_printer_states(msg_name, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_model")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["name"], "Bambu Lab A1 mini 2")

        # 3. Choose model
        msg_model = self._create_message("🖨️ A1 mini")
        handled = await handle_printer_states(msg_model, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_ip")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["printer_model"], "A1 mini")

        # 4. Enter IP
        msg_ip = self._create_message("192.168.1.99")
        handled = await handle_printer_states(msg_ip, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_code")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["ip"], "192.168.1.99")

        # 5. Enter access code
        msg_code = self._create_message("99887766")
        handled = await handle_printer_states(msg_code, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_sn")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["access_code"], "99887766")

        # 6. Enter serial number (Final step)
        msg_sn = self._create_message("0309DA999999999")
        handled = await handle_printer_states(msg_sn, self.app)
        self.assertTrue(handled)

        # Assertions
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data["context_data"])
        self.assertEqual(len(self.app.printers), 1)

        p_id = list(self.app.printers.keys())[0]
        p_obj = self.app.printers[p_id]

        # Ensure printer is BambuPrinter object and NOT a dict
        self.assertIsInstance(p_obj, BambuPrinter)
        self.assertEqual(p_obj.name, "Bambu Lab A1 mini 2")
        self.assertEqual(p_obj.ip, "192.168.1.99")
        self.assertEqual(p_obj.access_code, "99887766")
        self.assertEqual(p_obj.serial_number, "0309DA999999999")

        # Ensure methods and telemetry work without AttributeError
        storage_dict = p_obj.to_storage_dict()
        self.assertIsInstance(storage_dict, dict)
        self.assertEqual(storage_dict["name"], "Bambu Lab A1 mini 2")

        # Ensure keyboards generation works
        kb = get_printers_keyboard(self.app.printers)
        self.assertTrue(any("Bambu Lab A1 mini 2" in b.text for row in kb.keyboard for b in row))

        # Ensure telemetry builder works
        telemetry = build_printer_telemetry(p_obj)
        self.assertEqual(telemetry["name"], "Bambu Lab A1 mini 2")

    def test_defensive_telemetry_and_keyboards_with_dict(self):
        fake_printers = {
            "p1": {
                "id": "p1",
                "name": "Dict Printer",
                "ip": "1.2.3.4",
                "serial_number": "12345",
            }
        }
        kb = get_printers_keyboard(fake_printers)
        self.assertTrue(any("Dict Printer" in b.text for row in kb.keyboard for b in row))

        telem = build_printer_telemetry(fake_printers["p1"])
        self.assertEqual(telem["name"], "Dict Printer")
        self.assertEqual(telem["id"], "p1")
