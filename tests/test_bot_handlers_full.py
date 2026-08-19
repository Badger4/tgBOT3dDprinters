"""
Full coverage end-to-end unit tests for all Telegram bot handlers:
Dashboard, History, CSV Export, Printer Status, Filament, AMS Slots, Maintenance, and Callbacks.
"""

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers import setup_routers
from storage.manager import StorageManager


class TestBotHandlersFull(unittest.TestCase):
    def setUp(self):
        self.router = setup_routers()
        self.sm = StorageManager(Path("./printers_storage"))
        self.app = MagicMock()
        self.app.storage = self.sm
        self.app.printers = {}
        self.app.is_user_approved = AsyncMock(return_value=True)
        self.app.is_user_admin = AsyncMock(return_value=True)
        self.app.save_printers_config = AsyncMock()

        self.chat = Chat(id=777, type="private")
        self.user_obj = User(id=777, is_bot=False, first_name="Tester")

    async def _send_msg(self, text: str) -> AsyncMock:
        msg = Message(message_id=101, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text=text)
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_document", mock_answer)
        await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
        return mock_answer

    async def _send_cb(self, data: str) -> AsyncMock:
        msg = Message(message_id=101, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text="")
        mock_reply = AsyncMock()
        object.__setattr__(msg, "reply", mock_reply)
        cb = CallbackQuery(id="cb_test", from_user=self.user_obj, chat_instance="1", message=msg, data=data)
        mock_cb_answer = AsyncMock()
        object.__setattr__(cb, "answer", mock_cb_answer)
        await self.router.propagate_event("callback_query", cb, app=self.app, bot=self.app.bot)
        return mock_reply

    def test_all_handlers_and_buttons(self):
        async def run_test():
            await self.sm.save_user({"user_id": "777", "chat_id": "777", "state": "idle", "context_data": {}})

            # 1. Start / Navigation
            ans_start = await self._send_msg("/start")
            self.assertTrue(ans_start.called)

            # 2. Farm Dashboard (Empty)
            ans_dash = await self._send_msg("📊 Стан ферми")
            self.assertTrue(ans_dash.called)

            # Add a mock printer
            mock_printer = MagicMock()
            mock_printer.id = "p1"
            mock_printer.name = "Bambu Lab P1S"
            mock_printer.gcode_state = "IDLE"
            mock_printer.nozzle_temper = 210
            mock_printer.bed_temper = 60
            mock_printer.mc_percent = 0
            mock_printer.mc_remaining_time = 0
            mock_printer.layer_num = 0
            mock_printer.total_layer_num = 0
            mock_printer.subtask_name = ""
            mock_printer.filament_type = "PLA"
            mock_printer.filament_grams = 800.0
            mock_printer.price_per_kg = 650.0
            mock_printer.last_job_grams = 0.0
            mock_printer.total_print_hours = 45.0
            mock_printer.maintenance_hours_counter = 45.0
            mock_printer.maintenance_interval_hours = 100
            mock_printer.ip = "192.168.1.50"
            mock_printer.access_code = "12345678"
            mock_printer.serial_number = "00M00A000000000"
            mock_printer.ams_units = []

            self.app.printers = {"p1": mock_printer}

            # Farm Dashboard (With printer)
            ans_dash2 = await self._send_msg("📊 Стан ферми")
            self.assertTrue(ans_dash2.called)
            self.assertIn("Bambu Lab P1S", ans_dash2.call_args[0][0])

            # 3. History & CSV Export
            ans_hist = await self._send_msg("📜 Історія друку")
            self.assertTrue(ans_hist.called)

            ans_csv = await self._send_msg("📥 Завантажити CSV звіт")
            self.assertTrue(ans_csv.called)

            # 4. Printers List & Status
            ans_p_list = await self._send_msg("🖨️ Принтери")
            self.assertTrue(ans_p_list.called)

            # Select printer
            ans_sel_p = await self._send_msg("🖨️ Bambu Lab P1S")
            self.assertTrue(ans_sel_p.called)

            # Printer Status
            ans_status = await self._send_msg("📊 Статус")
            self.assertTrue(ans_status.called)
            self.assertIn("Напрацювання", ans_status.call_args[0][0])

            # Reset Maintenance Button
            ans_maint = await self._send_msg("🧹 Скинути лічильник ТО")
            self.assertTrue(ans_maint.called)

            # 5. Filament Menu
            ans_fil = await self._send_msg("📦 Склад")
            self.assertTrue(ans_fil.called)

            # 6. 3MF Commercial Calculation Flow (including direct button click with idle state)
            await self.sm.save_user(
                {
                    "user_id": "777",
                    "chat_id": "777",
                    "state": "idle",
                    "context_data": {
                        "pending_file": {
                            "filename": "heavy_8days_model.3mf",
                            "file_id": "file_123",
                            "local_filepath": "dummy.3mf",
                            "plate_name": "plate_1.gcode",
                            "printer_model": "Bambu Lab P1S",
                            "filament_type": "PLA",
                            "weight_g": 350.0,
                            "time_mins": 12661,
                        }
                    },
                }
            )

            ans_c3mf = await self._send_msg("💰 Розрахувати комерційну вартість 3MF")
            self.assertTrue(ans_c3mf.called)
            self.assertIn("Оберіть комерційний пресет", ans_c3mf.call_args[0][0])

            # Simulate state reset to idle and click "📊 Розрахувати для всіх пресетів"
            user_reset = await self.sm.load_user("777")
            user_reset["state"] = "idle"
            await self.sm.save_user(user_reset)

            ans_all_p = await self._send_msg("📊 Розрахувати для всіх пресетів")
            self.assertTrue(ans_all_p.called)
            self.assertIn("12661 хв", ans_all_p.call_args[0][0])
            self.assertNotIn("Скористайтесь кнопками", ans_all_p.call_args[0][0])

            # 7. Callbacks Testing
            cb_ans = await self._send_cb("notify_maint_reset_p1")
            self.assertTrue(mock_printer.reset_maintenance_counter.called)

        import asyncio

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
