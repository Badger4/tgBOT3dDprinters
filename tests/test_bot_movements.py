"""
Unit tests for Telegram Bot warehouse movements audit log and PDF export features.
"""

import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers import setup_routers
from models.printer import BambuPrinter
from storage.manager import StorageManager


class TestBotMovements(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)
        self.sm = StorageManager(self.temp_dir)

        self.router = setup_routers()
        self.app = MagicMock()
        self.app.storage = self.sm
        self.app.printers = {}
        self.app.is_user_approved = AsyncMock(return_value=True)
        self.app.is_user_admin = AsyncMock(return_value=True)
        self.app.save_printers_config = AsyncMock()

        self.chat = Chat(id=777, type="private")
        self.user_obj = User(id=777, is_bot=False, first_name="Tester", username="tester")

    def tearDown(self):
        if hasattr(self, "temp_dir_obj"):
            self.temp_dir_obj.cleanup()

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
        mock_edit = AsyncMock()
        mock_ans_doc = AsyncMock()
        object.__setattr__(msg, "edit_text", mock_edit)
        object.__setattr__(msg, "answer_document", mock_ans_doc)
        object.__setattr__(msg, "answer", AsyncMock())

        cb = CallbackQuery(id="cb_test", from_user=self.user_obj, chat_instance="1", message=msg, data=data)
        mock_cb_answer = AsyncMock()
        object.__setattr__(cb, "answer", mock_cb_answer)
        await self.router.propagate_event("callback_query", cb, app=self.app, bot=self.app.bot)
        return msg

    def test_movements_view_empty_and_populated(self):
        async def run_test():
            await self.sm.save_user({"user_id": "777", "chat_id": "777", "state": "idle", "context_data": {}})

            # 1. Empty movements view
            ans1 = await self._send_msg("📜 Аудит руху")
            self.assertTrue(ans1.called)
            text1 = ans1.call_args[0][0]
            self.assertIn("порожній", text1.lower())

            # 2. Seed movements
            await self.sm.record_spool_movement(
                spool_id="spool_1",
                spool_name="Bambu PLA Red",
                action="initial_stock",
                weight_change_g=1000.0,
                prev_weight_g=0.0,
                new_weight_g=1000.0,
                reason="Первинне внесення",
                user="Admin",
            )
            await self.sm.record_spool_movement(
                spool_id="spool_1",
                spool_name="Bambu PLA Red",
                action="refill",
                weight_change_g=200.0,
                prev_weight_g=1000.0,
                new_weight_g=1200.0,
                reason="Поповнення",
                user="Admin",
            )

            # 3. Populated movements view
            ans2 = await self._send_msg("📜 Аудит руху")
            self.assertTrue(ans2.called)
            text2 = ans2.call_args[0][0]
            self.assertIn("Bambu PLA Red", text2)
            self.assertIn("Поповнення", text2)
            self.assertIn("+200.0g", text2)

            # 4. Pagination & Filter callbacks
            msg_cb = await self._send_cb("mov_page:0:all")
            self.assertTrue(msg_cb.edit_text.called)

            msg_filter = await self._send_cb("mov_filter_menu")
            self.assertTrue(msg_filter.edit_text.called)

            msg_sel = await self._send_cb("mov_filter:spool_1")
            self.assertTrue(msg_sel.edit_text.called)

            msg_clear = await self._send_cb("mov_filter_clear")
            self.assertTrue(msg_clear.edit_text.called)

            # 5. Export PDF callbacks
            msg_pdf = await self._send_cb("mov_export_pdf")
            self.assertTrue(msg_pdf.answer_document.called)
            doc_arg = msg_pdf.answer_document.call_args[0][0]
            self.assertIn("spool_movements_audit", doc_arg.filename)

            msg_spools_pdf = await self._send_cb("pdf_export_spools")
            self.assertTrue(msg_spools_pdf.answer_document.called)

            msg_both = await self._send_cb("pdf_export_both")
            self.assertEqual(msg_both.answer_document.call_count, 2)

            # 6. Export PDF reply button
            ans_pdf_btn = await self._send_msg("📄 Експорт PDF")
            self.assertTrue(ans_pdf_btn.called)

        import asyncio
        asyncio.run(run_test())

    def test_spool_operations_audit_logging(self):
        async def run_test():
            await self.sm.save_user({"user_id": "777", "chat_id": "777", "state": "idle", "context_data": {}})

            # 1. Add spool via preset callback
            preset_data = {"name": "Audit Test PLA", "type": "PLA", "weight_g": 1000.0, "price_per_kg": 600.0, "color": "#ff0000"}
            await self.sm.save_presets({"p_test": preset_data})

            from bot.handlers.filament.add import handle_preset_callback
            cb = MagicMock()
            cb.from_user.id = 777
            cb.message.chat.id = 777
            cb.message.answer = AsyncMock()
            cb.answer = AsyncMock()
            cb.data = "preset:p_test"

            await handle_preset_callback(cb, self.app)

            # Check audit log contains initial_stock
            movements = await self.sm.load_spool_movements()
            self.assertEqual(len(movements), 1)
            self.assertEqual(movements[0]["action"], "initial_stock")
            self.assertEqual(movements[0]["spool_name"], "Audit Test PLA")
            self.assertEqual(movements[0]["weight_change_g"], 1000.0)

            spool_id = movements[0]["spool_id"]

            # 2. Edit spool weight
            await self.sm.save_user({
                "user_id": "777",
                "chat_id": "777",
                "state": "edit_spool_grams",
                "context_data": {"edit_spool_id": spool_id},
            })
            await self._send_msg("850")

            movements = await self.sm.load_spool_movements()
            self.assertEqual(len(movements), 2)
            self.assertEqual(movements[1]["action"], "manual_edit")
            self.assertEqual(movements[1]["weight_change_g"], -150.0)
            self.assertEqual(movements[1]["new_weight_g"], 850.0)

            # 3. Delete spool
            await self.sm.save_user({
                "user_id": "777",
                "chat_id": "777",
                "state": "confirm_delete_spool",
                "context_data": {"delete_spool_id": spool_id},
            })
            await self._send_msg("Так, видалити")

            movements = await self.sm.load_spool_movements()
            self.assertEqual(len(movements), 3)
            self.assertEqual(movements[2]["action"], "write_off")
            self.assertEqual(movements[2]["weight_change_g"], -850.0)
            self.assertEqual(movements[2]["new_weight_g"], 0.0)

        import asyncio
        asyncio.run(run_test())

    def test_printer_auto_deduct_audit_logging(self):
        async def run_test():
            # Setup a printer and a mounted spool in slot 0
            p_config = {
                "id": "p_audit_test",
                "name": "Audit Bambu",
                "ip": "127.0.0.1",
                "accessCode": "12345678",
                "serialNumber": "0123456789",
                "ams_slots": {"0": 1000.0},
            }
            printer = BambuPrinter(p_config, self.sm)
            self.app.printers["p_audit_test"] = printer

            await self.sm.save_spools({
                "spool_mounted": {
                    "id": "spool_mounted",
                    "name": "Mounted Audit PLA",
                    "remaining_grams": 1000.0,
                    "assigned_printer_id": "p_audit_test",
                    "assigned_slot_key": "0",
                }
            })

            # Call _deduct_spool_warehouse
            printer._deduct_spool_warehouse("0", 75.5)

            # Wait a tick for background coroutine
            import asyncio
            await asyncio.sleep(0.1)

            spools = await self.sm.load_spools()
            self.assertEqual(spools["spool_mounted"]["remaining_grams"], 924.5)

            movements = await self.sm.load_spool_movements()
            self.assertEqual(len(movements), 1)
            self.assertEqual(movements[0]["action"], "print")
            self.assertEqual(movements[0]["weight_change_g"], -75.5)
            self.assertEqual(movements[0]["new_weight_g"], 924.5)
            self.assertEqual(movements[0]["user"], "Audit Bambu")

        import asyncio
        asyncio.run(run_test())

    def test_multi_level_filtering_workflows(self):
        async def run_test():
            await self.sm.save_user({"user_id": "777", "chat_id": "777", "state": "idle", "context_data": {}})
            await self.sm.save_spools({
                "spool_a": {"id": "spool_a", "name": "Bambu Matte Black", "type": "PLA"},
                "spool_b": {"id": "spool_b", "name": "Devil Design Blue", "type": "PETG"},
            })

            # Seed movements
            now_ts = time.time()
            await self.sm.record_spool_movement(
                spool_id="spool_a",
                spool_name="Bambu Matte Black",
                action="initial_stock",
                weight_change_g=1000.0,
                prev_weight_g=0.0,
                new_weight_g=1000.0,
                reason="Arrival",
                user="Admin",
            )
            await self.sm.record_spool_movement(
                spool_id="spool_a",
                spool_name="Bambu Matte Black",
                action="print",
                weight_change_g=-120.0,
                prev_weight_g=1000.0,
                new_weight_g=880.0,
                reason="Model Drone_Arm_v2",
                user="Printer A1",
            )
            await self.sm.record_spool_movement(
                spool_id="spool_b",
                spool_name="Devil Design Blue",
                action="refill",
                weight_change_g=500.0,
                prev_weight_g=500.0,
                new_weight_g=1000.0,
                reason="Added extra",
                user="Admin",
            )

            # 1. Open filter hub
            msg_hub = await self._send_cb("mov_filter_menu")
            self.assertTrue(msg_hub.edit_text.called)
            hub_text = msg_hub.edit_text.call_args[0][0]
            self.assertIn("Панель фільтрів", hub_text)

            # 2. Date submenu & Set Date
            msg_date = await self._send_cb("mov_f_date_menu")
            self.assertTrue(msg_date.edit_text.called)
            msg_set_date = await self._send_cb("mov_f_set_date:today")
            self.assertTrue(msg_set_date.edit_text.called)

            # 3. Action submenu & Set Action
            msg_act = await self._send_cb("mov_f_action_menu")
            self.assertTrue(msg_act.edit_text.called)
            msg_set_act = await self._send_cb("mov_f_set_act:print")
            self.assertTrue(msg_set_act.edit_text.called)

            # 4. Spool submenu & Set Spool
            msg_spool = await self._send_cb("mov_f_spool_menu:0")
            self.assertTrue(msg_spool.edit_text.called)
            msg_set_spool = await self._send_cb("mov_f_set_spool:spool_a")
            self.assertTrue(msg_set_spool.edit_text.called)

            # 5. Return to log and verify filtered content
            msg_back = await self._send_cb("mov_f_back")
            self.assertTrue(msg_back.edit_text.called)
            back_text = msg_back.edit_text.call_args[0][0]
            self.assertIn("Drone_Arm_v2", back_text)
            self.assertNotIn("Devil Design Blue", back_text)

            # 6. Search query workflow: prompt then user message
            msg_prompt = await self._send_cb("mov_f_search_prompt")
            self.assertTrue(msg_prompt.edit_text.called)

            # Send message "Drone"
            ans_search = await self._send_msg("Drone")
            self.assertTrue(ans_search.called)
            search_text = ans_search.call_args[0][0]
            self.assertIn("Drone_Arm_v2", search_text)

            # 7. Direct spool shortcut
            msg_direct = await self._send_cb("mov_spool_direct:spool_b")
            self.assertTrue(msg_direct.edit_text.called)
            direct_text = msg_direct.edit_text.call_args[0][0]
            self.assertIn("Devil Design Blue", direct_text)
            self.assertNotIn("Drone_Arm_v2", direct_text)

            # 8. Reset all filters
            msg_clear = await self._send_cb("mov_f_clear")
            self.assertTrue(msg_clear.edit_text.called)

            # 9. PDF export with filtered movements
            await self._send_cb("mov_f_set_spool:spool_a")
            msg_pdf = await self._send_cb("mov_export_pdf")
            self.assertTrue(msg_pdf.answer_document.called)

        import asyncio
        asyncio.run(run_test())
