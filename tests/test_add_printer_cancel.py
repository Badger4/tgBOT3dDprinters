import unittest
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Chat, Message

from bot.handlers.printers import handle_printer_states


class TestAddPrinterCancel(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = MagicMock()
        self.app.printers = {}
        self.app.storage = MagicMock()
        self.app.is_user_approved = AsyncMock(return_value=True)

        self.user_data = {
            "state": "add_p_name",
            "context_data": {"new_printer": {"name": "Test"}},
        }
        self.app.storage.load_user = AsyncMock(return_value=self.user_data)
        self.app.storage.save_user = AsyncMock()

    async def test_cancel_at_add_p_name(self):
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "Відміна"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)

        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data.get("context_data", {}))
        self.app.storage.save_user.assert_called_once()
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0][0]
        self.assertIn("скасовано", call_args)

    async def test_cancel_at_add_p_ip(self):
        self.user_data["state"] = "add_p_ip"
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "скасувати"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)

        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data.get("context_data", {}))
        self.app.storage.save_user.assert_called_once()

    async def test_cancel_at_add_p_code(self):
        self.user_data["state"] = "add_p_code"
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "/cancel"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)

        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data.get("context_data", {}))

    async def test_cancel_at_add_p_model(self):
        self.user_data["state"] = "add_p_model"
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "скасувати"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)

        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data.get("context_data", {}))

    async def test_cancel_at_add_p_sn(self):
        self.user_data["state"] = "add_p_sn"
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "⬅️ Назад"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)

        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "idle")
        self.assertNotIn("new_printer", self.user_data.get("context_data", {}))

    async def test_add_printer_flow(self):
        self.user_data["state"] = "add_p_name"
        self.user_data["context_data"] = {"new_printer": {}}
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "My Printer"
        msg.answer = AsyncMock()

        handled = await handle_printer_states(msg, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_model")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["name"], "My Printer")

        msg.text = "🖨️ P1S"
        handled = await handle_printer_states(msg, self.app)
        self.assertTrue(handled)
        self.assertEqual(self.user_data["state"], "add_p_ip")
        self.assertEqual(self.user_data["context_data"]["new_printer"]["printer_model"], "P1S")


if __name__ == "__main__":
    unittest.main()
