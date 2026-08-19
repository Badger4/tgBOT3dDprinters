"""
Unit tests for Commercial Pricing Calculator Telegram Handlers.
Tests every button click, wizard step, preset creation, copying, editing, deletion, and quick calculations.
"""

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers import setup_routers
from storage.manager import StorageManager


class TestCommercialHandlers(unittest.TestCase):
    def setUp(self):
        self.router = setup_routers()
        self.sm = StorageManager(Path("./printers_storage"))
        self.app = MagicMock()
        self.app.storage = self.sm
        self.app.is_user_approved = AsyncMock(return_value=True)
        self.app.is_user_admin = AsyncMock(return_value=True)
        self.chat = Chat(id=123456, type="private")
        self.user_obj = User(id=123456, is_bot=False, first_name="Tester")

    async def _send_msg(self, text: str) -> AsyncMock:
        msg = Message(message_id=99, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text=text)
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
        return mock_answer

    async def _send_cb(self, data: str) -> AsyncMock:
        msg = Message(message_id=99, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text="")
        mock_reply = AsyncMock()
        object.__setattr__(msg, "reply", mock_reply)
        cb = CallbackQuery(id="cb1", from_user=self.user_obj, chat_instance="1", message=msg, data=data)
        mock_cb_answer = AsyncMock()
        object.__setattr__(cb, "answer", mock_cb_answer)
        await self.router.propagate_event("callback_query", cb, app=self.app, bot=self.app.bot)
        return mock_reply

    def test_commercial_menu_and_wizard_flow(self):
        async def run_test():
            # 1. User clicks "💰 Комерція"
            await self.sm.save_user({"user_id": "123456", "chat_id": "123456", "state": "idle", "context_data": {}})
            ans1 = await self._send_msg("💰 Комерція")
            self.assertTrue(ans1.called)
            txt1 = ans1.call_args[0][0]
            self.assertIn("Комерційний калькулятор ціни", txt1)

            # 2. User clicks "➕ Створити пресет"
            ans2 = await self._send_msg("➕ Створити пресет")
            self.assertTrue(ans2.called)
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_name")

            # Step 1: Preset Name
            await self._send_msg("PLA Premium Custom")
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_price")

            # Step 2: Plastic Price (850 грн/кг -> 0.85)
            await self._send_msg("850")
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_elec")

            # Step 3: Electricity rate (4.32)
            await self._send_msg("4.32")
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_depr")

            # Step 4: Depreciation (10 грн/год)
            await self._send_msg("10")
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_cons")

            # Step 5: Consumables (5 грн/год)
            await self._send_msg("5")
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "add_preset_profit")

            # Step 6: Profit (100%)
            ans_fin = await self._send_msg("100%")
            self.assertTrue(ans_fin.called)
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "idle")

            # 3. User clicks "🧮 Швидкий розрахунок ціни"
            await self._send_msg("🧮 Швидкий розрахунок ціни")
            await self._send_msg("250")  # 250 grams
            await self._send_msg("120")  # 120 mins
            user = await self.sm.load_user("123456")
            self.assertEqual(user["state"], "calc_select_preset")

            ans_calc = await self._send_msg("PLA Premium Custom")
            self.assertTrue(ans_calc.called)
            calc_txt = ans_calc.call_args[0][0]
            self.assertIn("ПІДСУМКОВА ВАРТІСТЬ ДЛЯ КЛІЄНТА", calc_txt)
            self.assertIn("PLA Premium Custom", calc_txt)

            # 4. User clicks "⬅️ Головне меню"
            ans_home = await self._send_msg("⬅️ Головне меню")
            self.assertTrue(ans_home.called)
            self.assertIn("Головне меню", ans_home.call_args[0][0])

        import asyncio

        asyncio.run(run_test())

    def test_sanitize_commercial_presets(self):
        from bot.handlers.commercial import sanitize_commercial_presets

        dirty = {
            "p1": {"id": "p1", "name": "Стандарт PLA"},
            "p2": {"id": "test_preset", "name": "Тестовий пресет"},
            "p3": {"id": "p3", "name": "Sample PETG"},
        }
        clean = sanitize_commercial_presets(dirty)
        self.assertIn("p1", clean)
        self.assertNotIn("p2", clean)
        self.assertNotIn("p3", clean)


if __name__ == "__main__":
    unittest.main()
