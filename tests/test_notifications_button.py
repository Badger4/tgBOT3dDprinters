import unittest
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Chat, Message

from bot.handlers.notifications import handle_notifications_menu


class TestNotificationsButton(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = MagicMock()
        self.app.storage = MagicMock()
        self.app.is_user_approved = AsyncMock(return_value=True)

        self.user_data = {
            "notify": {
                "start": True,
                "finish": True,
                "pause": True,
                "hms": True,
                "remind_clear": True,
            }
        }
        self.app.storage.load_user = AsyncMock(return_value=self.user_data)

    async def test_handle_notifications_full_button_text(self):
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "🔔 Налаштування сповіщень"
        msg.answer = AsyncMock()

        await handle_notifications_menu(msg, self.app)

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0][0]
        self.assertIn("Налаштування сповіщень", call_args)

    async def test_handle_notifications_short_button_text(self):
        msg = MagicMock(spec=Message)
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 12345
        msg.text = "🔔 Сповіщення"
        msg.answer = AsyncMock()

        await handle_notifications_menu(msg, self.app)

        msg.answer.assert_called_once()
        call_args = msg.answer.call_args[0][0]
        self.assertIn("Налаштування сповіщень", call_args)


if __name__ == "__main__":
    unittest.main()
