"""
Unit tests for interactive print history filtering, pagination, and PDF export in Telegram bot.
"""

import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers import setup_routers
from bot.handlers.dashboard import (
    filter_history_records,
    get_filter_labels,
    render_history_text,
)
from bot.keyboards import (
    get_history_date_filter_keyboard,
    get_history_inline_keyboard,
    get_history_printer_filter_keyboard,
)
from storage.manager import StorageManager


class TestHistoryFilter(unittest.TestCase):
    def setUp(self):
        self.router = setup_routers()
        self.sm = StorageManager(Path("./printers_storage"))
        self.app = MagicMock()
        self.app.storage = self.sm

        mock_p1 = MagicMock()
        mock_p1.id = "p1"
        mock_p1.name = "Bambu Lab P1S"
        mock_p1.serial_number = "00M001"

        mock_p2 = MagicMock()
        mock_p2.id = "p2"
        mock_p2.name = "Bambu Lab A1 mini"
        mock_p2.serial_number = "00M002"

        self.app.printers = {"p1": mock_p1, "p2": mock_p2}
        self.app.is_user_approved = AsyncMock(return_value=True)
        self.app.is_user_admin = AsyncMock(return_value=True)

        self.chat = Chat(id=888, type="private")
        self.user_obj = User(id=888, is_bot=False, first_name="HistTester")

    def test_filter_history_records(self):
        now = time.time()
        records = [
            {"timestamp": now - 3600, "printer_name": "Bambu Lab P1S", "printer_id": "p1", "subtask_name": "Job 1", "weight_g": 10},
            {"timestamp": now - 86400 * 3, "printer_name": "Bambu Lab A1 mini", "printer_id": "p2", "subtask_name": "Job 2", "weight_g": 20},
            {"timestamp": now - 86400 * 15, "printer_name": "Bambu Lab P1S", "printer_id": "p1", "subtask_name": "Job 3", "weight_g": 30},
            {"timestamp": now - 86400 * 45, "printer_name": "Bambu Lab A1 mini", "printer_id": "p2", "subtask_name": "Job 4", "weight_g": 40},
        ]

        # All
        res = filter_history_records(records, self.app, "all", "all")
        self.assertEqual(len(res), 4)

        # By printer p1
        res_p1 = filter_history_records(records, self.app, "p1", "all")
        self.assertEqual(len(res_p1), 2)
        self.assertEqual(res_p1[0]["subtask_name"], "Job 1")
        self.assertEqual(res_p1[1]["subtask_name"], "Job 3")

        # By date today
        res_today = filter_history_records(records, self.app, "all", "today")
        self.assertEqual(len(res_today), 1)
        self.assertEqual(res_today[0]["subtask_name"], "Job 1")

        # By date 7d
        res_7d = filter_history_records(records, self.app, "all", "7d")
        self.assertEqual(len(res_7d), 2)

        # By date 30d and printer p2
        res_30d_p2 = filter_history_records(records, self.app, "p2", "30d")
        self.assertEqual(len(res_30d_p2), 1)
        self.assertEqual(res_30d_p2[0]["subtask_name"], "Job 2")

    def test_keyboards(self):
        kb_main = get_history_inline_keyboard(self.app, printer_filter="p1", date_filter="today", page=1, total_pages=2)
        self.assertIsNotNone(kb_main)
        # Should have filter row, pagination row, and action row
        self.assertEqual(len(kb_main.inline_keyboard), 3)

        kb_printers = get_history_printer_filter_keyboard(self.app, current_filter="p1")
        self.assertIsNotNone(kb_printers)
        self.assertTrue(any("✅" in btn.text for row in kb_printers.inline_keyboard for btn in row))

        kb_dates = get_history_date_filter_keyboard(current_filter="7d")
        self.assertIsNotNone(kb_dates)
        self.assertTrue(any("✅" in btn.text for row in kb_dates.inline_keyboard for btn in row))

    def test_render_history_text(self):
        records = [
            {"timestamp": time.time(), "printer_name": "P1S", "subtask_name": "TestModel.gcode", "weight_g": 15.5, "filament_type": "PLA", "note": "OK"}
        ]
        txt_uk = render_history_text(records, "Усі принтери", "Сьогодні", 1, 1, is_en=False)
        self.assertIn("Журнал", txt_uk)
        self.assertIn("TestModel.gcode", txt_uk)
        self.assertIn("15.5g", txt_uk)

        txt_en = render_history_text([], "All printers", "All time", 1, 1, is_en=True)
        self.assertIn("No print jobs match the selected filters", txt_en)

    def test_bot_history_callbacks_workflow(self):
        async def run_flow():
            # Setup user in storage
            await self.sm.save_user({"user_id": "888", "chat_id": "888", "state": "idle", "context_data": {}, "language": "uk"})

            # Seed history via mock
            now = time.time()
            test_history = [
                {"timestamp": now - 100 * i, "printer_name": "Bambu Lab P1S", "printer_id": "p1", "subtask_name": f"Part_{i}.gcode", "weight_g": 10.0 + i}
                for i in range(12)
            ]
            self.app.storage.load_history = AsyncMock(return_value=test_history)

            # 1. User sends "📜 Історія друку"
            msg = Message(message_id=201, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text="📜 Історія друку")
            mock_msg_answer = AsyncMock()
            object.__setattr__(msg, "answer", mock_msg_answer)
            await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
            self.assertTrue(mock_msg_answer.called)

            cb_msg = Message(message_id=202, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text="")
            mock_edit_text = AsyncMock()
            object.__setattr__(cb_msg, "edit_text", mock_edit_text)
            mock_doc_answer = AsyncMock()
            object.__setattr__(cb_msg, "answer_document", mock_doc_answer)

            def make_cb(data_str: str) -> CallbackQuery:
                c = CallbackQuery(id=f"cb_{data_str}", from_user=self.user_obj, chat_instance="1", message=cb_msg, data=data_str)
                object.__setattr__(c, "answer", AsyncMock())
                return c

            # 2. Callback hist_menu_p
            await self.router.propagate_event("callback_query", make_cb("hist_menu_p"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 3. Callback hist_p:p1
            mock_edit_text.reset_mock()
            await self.router.propagate_event("callback_query", make_cb("hist_p:p1"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 4. Callback hist_menu_d
            mock_edit_text.reset_mock()
            await self.router.propagate_event("callback_query", make_cb("hist_menu_d"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 5. Callback hist_d:today
            mock_edit_text.reset_mock()
            await self.router.propagate_event("callback_query", make_cb("hist_d:today"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 6. Callback hist_page:2
            mock_edit_text.reset_mock()
            await self.router.propagate_event("callback_query", make_cb("hist_page:2"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 7. Callback hist_reset
            mock_edit_text.reset_mock()
            await self.router.propagate_event("callback_query", make_cb("hist_reset"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_edit_text.called)

            # 8. Callback hist_export_pdf
            await self.router.propagate_event("callback_query", make_cb("hist_export_pdf"), app=self.app, bot=self.app.bot)
            self.assertTrue(mock_doc_answer.called)

        import asyncio
        asyncio.run(run_flow())


if __name__ == "__main__":
    unittest.main()
