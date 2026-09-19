"""
Comprehensive automated tests for all filament warehouse workflows:
- Adding spool (valid and invalid inputs)
- Editing spool (name, type, grams with math/invalid, price with invalid)
- Mounting spool (verifying printer selection router fix: no hijacking by view_printer)
- Mounting to AMS and non-AMS printers
- Unmounting spool
- Deleting spool (confirmation and cancel)
- Back / cancel button behavior in every state
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


class TestFilamentComprehensiveWorkflow(unittest.IsolatedAsyncioTestCase):
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

        # Printer 1: P1S with AMS
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
        self.p1.ams_slots = {"0": 1000.0, "1": 1000.0, "2": 1000.0, "3": 1000.0, "254": 0.0}
        self.p1.ams_trays_info = {
            "0": {"empty": False, "type": "PLA", "sub_brands": "Basic"},
            "1": {"empty": True, "type": ""},
            "2": {"empty": True, "type": ""},
            "3": {"empty": True, "type": ""},
        }

        # Printer 2: A1 mini WITHOUT AMS
        self.p2 = BambuPrinter(
            {
                "id": "p2",
                "name": "Bambu Lab A1 mini 2",
                "ip": "192.168.1.20",
                "accessCode": "87654321",
                "serialNumber": "01A1M000000002",
                "printer_model": "A1 mini",
                "ams_enabled": False,
            },
            storage=self.app.storage,
        )
        self.p2.ams_slots = {"254": 500.0}
        self.p2.ams_trays_info = {"254": {"empty": False, "type": "PETG"}}

        self.app.printers = {"p1": self.p1, "p2": self.p2}

        # Seed sample spools
        await self.app.storage.save_spools({
            "spool_1": {
                "id": "spool_1",
                "name": "Bambu PLA Basic Black",
                "type": "PLA",
                "color": "#000000",
                "remaining_grams": 1000.0,
                "price_per_kg": 850.0,
                "assigned_printer_id": None,
                "assigned_slot_key": None,
            },
            "spool_2": {
                "id": "spool_2",
                "name": "Sunlu PETG White",
                "type": "PETG",
                "color": "#FFFFFF",
                "remaining_grams": 750.0,
                "price_per_kg": 650.0,
                "assigned_printer_id": None,
                "assigned_slot_key": None,
            },
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

        # Propagate through router
        await self.router.propagate_event(
            update_type="message",
            event=msg,
            app=self.app,
            bot=self.bot,
        )
        return mock_answer

    async def test_spool_editing_flow_valid_and_invalid(self):
        """Test full spool editing flow with valid and invalid inputs."""
        # 1. Open Warehouse
        ans = await self._send("📦 Склад")
        self.assertTrue(ans.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")

        # 2. Click Edit Spool
        ans = await self._send("✏️ Редагувати")
        self.assertTrue(ans.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_edit")

        # 2.1 Invalid spool selection
        ans_inv = await self._send("Котушка яка не існує")
        self.assertTrue(ans_inv.called)
        self.assertIn("Оберіть котушку зі списку", ans_inv.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_edit")

        # 2.2 Valid spool selection
        ans_spool = await self._send("🧵 Bambu PLA Basic Black (1000.0g)")
        self.assertTrue(ans_spool.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_field")
        self.assertEqual(u["context_data"]["edit_spool_id"], "spool_1")

        # 2.3 Invalid field selection
        ans_inv_field = await self._send("Невідомий параметр")
        self.assertTrue(ans_inv_field.called)
        self.assertIn("оберіть параметр", ans_inv_field.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_field")

        # 2.4 Edit Name
        ans_name_btn = await self._send("🏷️ Назва")
        self.assertTrue(ans_name_btn.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_name")

        ans_new_name = await self._send("Bambu PLA Premium Black")
        self.assertTrue(ans_new_name.called)
        self.assertIn("змінено", ans_new_name.call_args[0][0].lower())
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["spool_1"]["name"], "Bambu PLA Premium Black")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")

        # 2.5 Edit Grams with Invalid math / negative / string, then valid math
        await self._send("✏️ Редагувати")
        await self._send("Bambu PLA Premium Black")
        await self._send("⚖️ Залишок (г)")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_grams")

        # Invalid string
        ans_bad1 = await self._send("багато грам")
        self.assertTrue(ans_bad1.called)
        self.assertIn("Некоректне", ans_bad1.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_grams")

        # Negative number
        ans_bad2 = await self._send("-200")
        self.assertTrue(ans_bad2.called)
        self.assertIn("Некоректне", ans_bad2.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_grams")

        # Division by zero
        ans_bad3 = await self._send("1000 / 0")
        self.assertTrue(ans_bad3.called)
        self.assertIn("Некоректне", ans_bad3.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_grams")

        # Valid math formula: 1000 - 150
        ans_good_g = await self._send("1000 - 150")
        self.assertTrue(ans_good_g.called)
        self.assertIn("850", ans_good_g.call_args[0][0])
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["spool_1"]["remaining_grams"], 850.0)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")

        # 2.6 Edit Price with Invalid then valid
        await self._send("✏️ Редагувати")
        await self._send("Bambu PLA Premium Black")
        await self._send("💰 Вартість (грн)")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_price")

        # Invalid price
        ans_bad_pr = await self._send("безкоштовно")
        self.assertTrue(ans_bad_pr.called)
        self.assertIn("Некоректна", ans_bad_pr.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_spool_price")

        # Valid price: 920.5 грн
        ans_good_pr = await self._send("920.5 грн")
        self.assertTrue(ans_good_pr.called)
        self.assertIn("920.5", ans_good_pr.call_args[0][0])
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["spool_1"]["price_per_kg"], 920.5)

    async def test_mounting_flow_prevents_router_hijacking_and_supports_ams(self):
        """Test mounting flow: user selects spool, selects printer, verifies router DOES NOT open printer card."""
        # 1. Start mount from general warehouse (no printer in context)
        await self._send("📦 Склад")
        ans_mount = await self._send("🔗 Встановити на принтер")
        self.assertTrue(ans_mount.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_mount")

        # 2. Select spool
        ans_sel_sp = await self._send("🧵 Sunlu PETG White (750.0g)")
        self.assertTrue(ans_sel_sp.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_printer_for_mount")

        # 3. Test Invalid printer selection
        ans_bad_p = await self._send("🖨️ Epson L805")
        self.assertTrue(ans_bad_p.called)
        self.assertIn("Оберіть принтер", ans_bad_p.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_printer_for_mount")

        # 4. CRITICAL TEST: Select Bambu Lab P1S (starts with "🖨️ ")
        # Must NOT be intercepted by handle_select_printer (which would show printer status card)
        ans_p1 = await self._send("🖨️ Bambu Lab P1S")
        self.assertTrue(ans_p1.called)
        reply_txt = ans_p1.call_args[0][0]
        # It must NOT show "📊 Стан принтера" or "Access Code" or printer status card
        self.assertNotIn("📊 Стан принтера", reply_txt)
        # It must prompt for AMS slot because P1S has AMS!
        self.assertIn("Оберіть слот AMS", reply_txt)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_mount")

        # 5. Invalid slot selection
        ans_bad_slot = await self._send("Слот 99")
        self.assertTrue(ans_bad_slot.called)
        self.assertIn("Невідомий слот", ans_bad_slot.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_mount")

        # 6. Valid slot selection: Slot A2
        ans_good_slot = await self._send("📍 Слот A2 (Slot 2)")
        self.assertTrue(ans_good_slot.called)
        replies_good_slot = " ".join(str(call[0][0]) for call in ans_good_slot.call_args_list)
        self.assertIn("встановлено", replies_good_slot.lower())
        self.assertIn("A2", replies_good_slot)

        spools = await self.app.storage.load_spools()
        mounted_s = spools["spool_2"]
        self.assertEqual(mounted_s["assigned_printer_id"], "p1")
        self.assertEqual(mounted_s["assigned_slot_key"], "1")
        self.assertEqual(self.p1.ams_slots["1"], 750.0)

    async def test_mounting_to_non_ams_printer_direct(self):
        """Test mounting spool to a printer without AMS: directly mounts to external slot 254."""
        await self._send("📦 Склад")
        await self._send("🔗 Встановити на принтер")
        await self._send("🧵 Bambu PLA Basic Black (1000.0g)")

        # Select A1 mini 2 (which has no AMS)
        ans_p2 = await self._send("🖨️ Bambu Lab A1 mini 2")
        self.assertTrue(ans_p2.called)
        replies_p2 = " ".join(str(call[0][0]) for call in ans_p2.call_args_list)
        self.assertIn("встановлено", replies_p2)
        self.assertIn("Зовнішній (VT)", replies_p2)

        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["spool_1"]["assigned_printer_id"], "p2")
        self.assertEqual(spools["spool_1"]["assigned_slot_key"], "254")
        self.assertEqual(self.p2.ams_slots["254"], 1000.0)

    async def test_unmounting_flow(self):
        """Test unmounting spool from a printer back to warehouse."""
        # First mount spool_2 to p1 slot 1
        spools = await self.app.storage.load_spools()
        spools["spool_2"]["assigned_printer_id"] = "p1"
        spools["spool_2"]["assigned_slot_key"] = "1"
        await self.app.storage.save_spools(spools)

        # In warehouse, click Unmount
        await self._send("📦 Склад")
        ans_unm = await self._send("🔓 Зняти з принтера")
        self.assertTrue(ans_unm.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_unmount")

        # Invalid selection
        ans_inv = await self._send("Невідома котушка")
        self.assertTrue(ans_inv.called)
        self.assertIn("Оберіть котушку зі списку", ans_inv.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_unmount")

        # Valid selection
        ans_ok = await self._send("Sunlu PETG White")
        self.assertTrue(ans_ok.called)
        replies_ok = " ".join(str(call[0][0]) for call in ans_ok.call_args_list)
        self.assertIn("знято", replies_ok.lower())

        spools = await self.app.storage.load_spools()
        self.assertIsNone(spools["spool_2"]["assigned_printer_id"])
        self.assertIsNone(spools["spool_2"]["assigned_slot_key"])

    async def test_spool_deleting_cancel_and_confirm(self):
        """Test spool deleting flow with cancellation and confirmation."""
        # 1. Start delete
        await self._send("📦 Склад")
        ans_del = await self._send("🗑️ Видалити")
        self.assertTrue(ans_del.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_spool_to_delete")

        # 2. Select spool
        ans_sel = await self._send("🧵 Sunlu PETG White (750.0g)")
        self.assertTrue(ans_sel.called)
        self.assertIn("Ви впевнені", ans_sel.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "confirm_delete_spool")

        # 3. Click Cancel
        ans_cancel = await self._send("❌ Скасувати")
        self.assertTrue(ans_cancel.called)
        self.assertIn("скасовано", ans_cancel.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")
        # Ensure spool still exists
        spools = await self.app.storage.load_spools()
        self.assertIn("spool_2", spools)

        # 4. Now confirm delete
        await self._send("🗑️ Видалити")
        await self._send("Sunlu PETG White")
        ans_confirm = await self._send("🗑️ Так, видалити")
        self.assertTrue(ans_confirm.called)
        self.assertIn("успішно видалено", ans_confirm.call_args[0][0].lower())

        spools = await self.app.storage.load_spools()
        self.assertNotIn("spool_2", spools)

    async def test_add_spool_flow_defensive_validation(self):
        """Test adding spool with defensive validation on color, grams, price and quantity."""
        await self._send("📦 Склад")
        ans_add = await self._send("➕ Додати")
        self.assertTrue(ans_add.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_name")

        # Enter name
        await self._send("Devil Design PETG Red")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_type")

        # Enter type
        await self._send("PETG")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_color")

        # Enter color
        await self._send("🔴 Червоний")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")

        # Enter invalid grams (string)
        ans_bad_g1 = await self._send("невідомо")
        self.assertTrue(ans_bad_g1.called)
        self.assertIn("коректну вагу", ans_bad_g1.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")

        # Enter invalid grams (negative)
        ans_bad_g2 = await self._send("-500")
        self.assertTrue(ans_bad_g2.called)
        self.assertIn("коректну вагу", ans_bad_g2.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")

        # Enter valid grams
        await self._send("1000g")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_price")

        # Enter invalid price
        ans_bad_pr = await self._send("безплатно")
        self.assertTrue(ans_bad_pr.called)
        self.assertIn("коректну ціну", ans_bad_pr.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_price")

        # Enter valid price
        await self._send("780 грн")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_quantity")

        # Enter invalid quantity
        ans_bad_qty = await self._send("багато")
        self.assertTrue(ans_bad_qty.called)
        self.assertIn("коректну кількість", ans_bad_qty.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_quantity")

        # Enter valid quantity
        ans_ok = await self._send("1 шт")
        self.assertTrue(ans_ok.called)
        self.assertIn("успішно додано", ans_ok.call_args[0][0].lower())

        spools = await self.app.storage.load_spools()
        added = next((s for s in spools.values() if s.get("name") == "Devil Design PETG Red"), None)
        self.assertIsNotNone(added)
        self.assertEqual(added["remaining_grams"], 1000.0)
        self.assertEqual(added["price_per_kg"], 780.0)
        self.assertEqual(added["color"], "#EF4444")
        self.assertEqual(added["quantity"], 1)

    async def test_back_button_cancels_at_any_state(self):
        """Test that Back button safely resets state from any active workflow state."""
        states_to_test = [
            ("add_spool_name", "➕ Додати"),
            ("select_spool_to_edit", "✏️ Редагувати"),
            ("select_spool_to_delete", "🗑️ Видалити"),
            ("select_spool_to_mount", "🔗 Встановити на принтер"),
        ]
        for expected_state, trigger_btn in states_to_test:
            await self._send("📦 Склад")
            await self._send(trigger_btn)
            u = await self.app.storage.load_user("999")
            self.assertEqual(u["state"], expected_state)

            ans_back = await self._send("⬅️ Назад")
            self.assertTrue(ans_back.called)
            self.assertIn("скасовано", ans_back.call_args[0][0].lower())
            u = await self.app.storage.load_user("999")
            self.assertEqual(u["state"], "idle")

    async def test_non_1000g_spool_handling_and_percentage(self):
        """Test that spools with arbitrary weights (e.g. 2500g, 250g) are supported and percentages calculate accurately."""
        await self._send("📦 Склад")
        await self._send("➕ Додати")
        await self._send("Big Reel PLA Black")
        await self._send("PLA")
        await self._send("⚫ Чорний")
        await self._send("2500")
        await self._send("1500")
        await self._send("1")

        spools = await self.app.storage.load_spools()
        big_spool = next((s for s in spools.values() if s.get("name") == "Big Reel PLA Black"), None)
        self.assertIsNotNone(big_spool)
        self.assertEqual(big_spool["initial_grams"], 2500.0)
        self.assertEqual(big_spool["remaining_grams"], 2500.0)

        # Mount to printer P1S slot A1
        await self._send("🔗 Встановити на принтер")
        await self._send("Big Reel PLA Black")
        await self._send("🖨️ Bambu Lab P1S")
        await self._send("A1 (Слот 1)")

        # Verify filament display shows 100%
        ans_view = await self._send("📦 Склад")
        self.assertTrue(ans_view.called)
        call_text = ans_view.call_args[0][0]
        self.assertIn("<b>2500.0g</b> (100%)", call_text)

        # Edit spool remaining to 1250g (half used) via printer slot
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)
        await self._send("✏️ Змінити вагу")
        await self._send("📍 Слот A1 (Slot 1)")
        await self._send("1250")

        # Verify filament display now shows 50%
        ans_view2 = await self._send("📦 Склад")
        self.assertTrue(ans_view2.called)
        call_text2 = ans_view2.call_args[0][0]
        self.assertIn("<b>1250.0g</b> (50%)", call_text2)

    async def test_manual_weight_edit_with_ams_printer_slot_selection(self):
        """Test that clicking '✏️ Змінити вагу' on AMS printer prompts for slot selection first."""
        # Set user context to P1S
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)

        # 1. Click edit weight
        ans = await self._send("✏️ Змінити вагу")
        self.assertTrue(ans.called)
        call_text = ans.call_args[0][0]
        self.assertIn("Оберіть слот AMS", call_text)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_weight")

        # 2. Select Slot A2
        ans2 = await self._send("📍 Слот A2 (Slot 2)")
        self.assertTrue(ans2.called)
        call_text2 = ans2.call_args[0][0]
        self.assertIn("Поточний залишок", call_text2)
        self.assertIn("Слот A2", call_text2)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_filament_weight")
        self.assertEqual(u["context_data"]["edit_weight_slot_key"], "1")

        # 3. Enter new weight
        ans3 = await self._send("800")
        self.assertTrue(ans3.called)
        call_text3 = ans3.call_args[0][0]
        self.assertIn("800.0g", call_text3)
        self.assertIn("Слот A2", call_text3)
        self.assertEqual(self.p1.get_slot_grams("1"), 800.0)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "printer_menu")

    async def test_manual_weight_edit_without_ams_printer_direct_prompt(self):
        """Test that clicking '✏️ Змінити вагу' on non-AMS printer asks for weight directly."""
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p2"
        await self.app.storage.save_user(u)

        ans = await self._send("✏️ Змінити вагу")
        self.assertTrue(ans.called)
        call_text = ans.call_args[0][0]
        self.assertIn("Введіть нову залишкову вагу", call_text)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "edit_filament_weight")

        ans2 = await self._send("450")
        self.assertTrue(ans2.called)
        call_text2 = ans2.call_args[0][0]
        self.assertIn("450.0g", call_text2)
        self.assertEqual(self.p2.get_slot_grams("254"), 450.0)

    async def test_manual_weight_edit_invalid_slot_and_back(self):
        """Test invalid slot text in select_slot_for_weight and cancelling via Back."""
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)

        await self._send("✏️ Змінити вагу")
        ans_inv = await self._send("Invalid Slot Button")
        self.assertTrue(ans_inv.called)
        self.assertIn("Невідомий слот", ans_inv.call_args[0][0])
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "select_slot_for_weight")

        ans_back = await self._send("⬅️ Назад")
        self.assertTrue(ans_back.called)
        self.assertIn("скасовано", ans_back.call_args[0][0].lower())
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "printer_menu")

    async def test_manual_weight_edit_syncs_mounted_spool(self):
        """Test that updating slot weight syncs the warehouse spool assigned to that slot."""
        # Mount spool_1 to p1 slot A3 (key "2")
        spools = await self.app.storage.load_spools()
        spools["spool_1"]["assigned_printer_id"] = "p1"
        spools["spool_1"]["assigned_slot_key"] = "2"
        await self.app.storage.save_spools(spools)

        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)

        await self._send("✏️ Змінити вагу")
        await self._send("📍 Слот A3 (Slot 3)")
        await self._send("625")

        self.assertEqual(self.p1.get_slot_grams("2"), 625.0)
        spools_after = await self.app.storage.load_spools()
        self.assertEqual(spools_after["spool_1"]["remaining_grams"], 625.0)

    async def test_zero_grams_renders_as_empty_not_fake_spool(self):
        """Test that a slot with 0.0g displays as 'Порожньо' (Empty) even if tray has a cached material type."""
        # Configure p2 (non-AMS) with 0.0g and tray_type "TPU"
        self.p2.ams_slots["254"] = 0.0
        self.p2.filament_grams = 0.0
        self.p2.ams_trays_info["254"] = {"id": "254", "empty": False, "type": "TPU"}
        self.p2.filament_type = "TPU"

        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p2"
        await self.app.storage.save_user(u)

        # 1. Check printer status
        ans_status = await self._send("📊 Статус")
        self.assertTrue(ans_status.called)
        status_text = ans_status.call_args[0][0]
        self.assertIn("Порожньо", status_text)
        self.assertNotIn("0.0g", status_text)

        # 2. Check filament view
        ans_fil = await self._send("🧵 Філамент")
        self.assertTrue(ans_fil.called)
        fil_text = ans_fil.call_args[0][0]
        self.assertIn("VT</b>: Порожньо", fil_text)
        self.assertNotIn("Bambu TPU — 0.0g", fil_text)

    async def test_add_spool_wizard_step_back_navigation(self):
        """Test step-by-step back navigation ('↩️ Крок назад') during spool creation wizard."""
        await self._send("📦 Склад")
        await self._send("➕ Додати")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_name")

        # 1. Enter initial name -> moves to add_spool_type
        await self._send("Original Spool Name")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_type")

        # 2. Step back from add_spool_type -> goes back to add_spool_name
        ans_back1 = await self._send("↩️ Крок назад")
        self.assertTrue(ans_back1.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_name")
        self.assertIn("Original Spool Name", ans_back1.call_args[0][0])

        # 3. Enter updated name -> moves to add_spool_type
        await self._send("Corrected Spool Name")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_type")

        # 4. Select filament type button -> moves to add_spool_color
        await self._send("PETG")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_color")
        self.assertEqual(u["context_data"]["new_spool"]["type"], "PETG")

        # 5. Step back from add_spool_color -> goes back to add_spool_type
        ans_back2 = await self._send("↩️ Крок назад")
        self.assertTrue(ans_back2.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_type")
        self.assertIn("PETG", ans_back2.call_args[0][0])

        # 6. Re-select filament type -> moves to add_spool_color
        await self._send("PLA")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_color")
        self.assertEqual(u["context_data"]["new_spool"]["type"], "PLA")

        # 7. Select color -> moves to add_spool_grams
        await self._send("⚫ Чорний")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")
        self.assertEqual(u["context_data"]["new_spool"]["color"], "#000000")

        # 8. Step back from add_spool_grams -> goes back to add_spool_color
        ans_back3 = await self._send("↩️ Крок назад")
        self.assertTrue(ans_back3.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_color")

        # 9. Re-select color -> moves to add_spool_grams
        await self._send("⚪ Білий")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")
        self.assertEqual(u["context_data"]["new_spool"]["color"], "#FFFFFF")

        # 10. Enter grams -> moves to add_spool_price
        await self._send("800")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_price")
        self.assertEqual(u["context_data"]["new_spool"]["remaining_grams"], 800.0)

        # 11. Step back from add_spool_price -> goes back to add_spool_grams
        ans_back4 = await self._send("↩️ Крок назад")
        self.assertTrue(ans_back4.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_grams")
        self.assertIn("800.0g", ans_back4.call_args[0][0])

        # 12. Enter final grams -> moves to add_spool_price
        await self._send("1000")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_price")

        # 13. Enter price -> moves to add_spool_quantity
        await self._send("750")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_quantity")

        # 14. Step back from add_spool_quantity -> goes back to add_spool_price
        ans_back5 = await self._send("↩️ Крок назад")
        self.assertTrue(ans_back5.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_price")
        self.assertIn("750.0 грн", ans_back5.call_args[0][0])

        # 15. Enter final price -> moves to add_spool_quantity
        await self._send("850")
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "add_spool_quantity")

        # 16. Enter quantity -> saves spool!
        ans_final = await self._send("7 шт")
        self.assertTrue(ans_final.called)
        u = await self.app.storage.load_user("999")
        self.assertEqual(u["state"], "idle")

        spools = await self.app.storage.load_spools()
        created = next((s for s in spools.values() if s.get("name") == "Corrected Spool Name"), None)
        self.assertIsNotNone(created)
        self.assertEqual(created["type"], "PLA")
        self.assertEqual(created["color"], "#FFFFFF")
        self.assertEqual(created["remaining_grams"], 1000.0)
        self.assertEqual(created["price_per_kg"], 850.0)
        self.assertEqual(created["quantity"], 7)

    async def test_spool_batch_quantity_mount_and_unmount_lifecycle(self):
        """Test full lifecycle of batch spools:
        1. Add spool with quantity=7
        2. Mount 1 to printer P1S Slot A1 -> warehouse has 6 left, printer has 1000g mounted
        3. Unmount without weight change (1000g) -> warehouse merges back to 7
        4. Mount 1 to printer again -> warehouse has 6 left
        5. Print occurred (weight changed to 850g)
        6. Unmount with changed weight (850g) -> warehouse has 6 (1000g) + 1 started (850g)
        """
        await self._send("📦 Склад")
        await self._send("➕ Додати")
        await self._send("Bambu PLA Basic Jade White")
        await self._send("PLA")
        await self._send("⚪ Білий")
        await self._send("1000")
        await self._send("850")
        await self._send("7 шт")

        spools = await self.app.storage.load_spools()
        batch_spool = next((s for s in spools.values() if s.get("name") == "Bambu PLA Basic Jade White"), None)
        self.assertIsNotNone(batch_spool)
        self.assertEqual(batch_spool["quantity"], 7)
        self.assertEqual(batch_spool["color"], "#FFFFFF")
        self.assertIsNone(batch_spool.get("assigned_printer_id"))
        parent_id = batch_spool["id"]

        # Step 1: Mount 1 spool to printer P1S slot A1
        await self._send("🔗 Встановити на принтер")
        await self._send("Bambu PLA Basic Jade White")
        await self._send("🖨️ Bambu Lab P1S")
        ans_mount1 = await self._send("📍 Слот A1 (Slot 1)")
        self.assertTrue(ans_mount1.called)
        replies_mount1 = " ".join(str(call[0][0]) for call in ans_mount1.call_args_list)
        self.assertIn("Залишок на Складі: <b>6 шт</b>", replies_mount1)

        # Verify storage: parent batch has quantity 6, mounted copy has quantity 1
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools[parent_id]["quantity"], 6)
        self.assertIsNone(spools[parent_id].get("assigned_printer_id"))

        mounted_spool = next((s for s in spools.values() if s.get("assigned_printer_id") == "p1" and str(s.get("assigned_slot_key")) == "0"), None)
        self.assertIsNotNone(mounted_spool)
        self.assertEqual(mounted_spool["quantity"], 1)
        self.assertEqual(mounted_spool["remaining_grams"], 1000.0)
        self.assertEqual(mounted_spool.get("parent_spool_id"), parent_id)

        # Step 2: Unmount spool WITHOUT weight change (weight is still 1000g)
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)

        ans_unm1 = await self._send("🔓 Зняти з принтера")
        self.assertTrue(ans_unm1.called)
        ans_unmount1 = await self._send("Bambu PLA Basic Jade White")
        self.assertTrue(ans_unmount1.called)
        replies_unmount1 = " ".join(str(call[0][0]) for call in ans_unmount1.call_args_list)
        self.assertIn("повернуто до пачки (разом: 7 шт)", replies_unmount1)

        # Verify storage: batch is back to 7, temporary mounted copy is deleted
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools[parent_id]["quantity"], 7)
        self.assertNotIn(mounted_spool["id"], spools)

        # Step 3: Mount 1 spool again to printer P1S slot A1
        await self._send("🔗 Встановити на принтер")
        await self._send("Bambu PLA Basic Jade White")
        await self._send("🖨️ Bambu Lab P1S")
        await self._send("📍 Слот A1 (Slot 1)")

        spools = await self.app.storage.load_spools()
        self.assertEqual(spools[parent_id]["quantity"], 6)
        mounted_spool2 = next((s for s in spools.values() if s.get("assigned_printer_id") == "p1" and str(s.get("assigned_slot_key")) == "0"), None)
        self.assertIsNotNone(mounted_spool2)

        # Step 4: Print occurred! Change weight on printer to 850g
        self.p1.set_slot_grams(850.0, slot_id="0")
        mounted_spool2["remaining_grams"] = 850.0
        spools[mounted_spool2["id"]] = mounted_spool2
        await self.app.storage.save_spools(spools)

        # Step 5: Unmount spool with changed weight (850g)
        u = await self.app.storage.load_user("999")
        u["context_data"]["selected_printer_id"] = "p1"
        await self.app.storage.save_user(u)

        ans_unm2 = await self._send("🔓 Зняти з принтера")
        self.assertTrue(ans_unm2.called)
        ans_unmount2 = await self._send("Bambu PLA Basic Jade White")
        self.assertTrue(ans_unmount2.called)
        replies_unmount2 = " ".join(str(call[0][0]) for call in ans_unmount2.call_args_list)
        self.assertIn("розпочата котушка: 850.0g (1 шт)", replies_unmount2)

        # Verify storage: parent batch STILL has 6 шт (1000g), AND a separate started spool exists with 850g (1 шт)!
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools[parent_id]["quantity"], 6)
        self.assertEqual(spools[parent_id]["remaining_grams"], 1000.0)

        started_spool = spools.get(mounted_spool2["id"])
        self.assertIsNotNone(started_spool)
        self.assertEqual(started_spool["quantity"], 1)
        self.assertEqual(started_spool["remaining_grams"], 850.0)
        self.assertIsNone(started_spool.get("assigned_printer_id"))
        self.assertNotIn("parent_spool_id", started_spool)

    async def test_spool_editing_color_and_quantity(self):
        """Test modifying color and quantity of an existing spool in stock."""
        # Create a spool in storage
        spools = await self.app.storage.load_spools()
        spools["s_edit"] = {
            "id": "s_edit",
            "name": "Sunlu PETG",
            "type": "PETG",
            "color": "#000000",
            "remaining_grams": 1000.0,
            "initial_grams": 1000.0,
            "price_per_kg": 650.0,
            "assigned_printer_id": None,
            "assigned_slot_key": None,
            "quantity": 1,
        }
        await self.app.storage.save_spools(spools)

        await self._send("📦 Склад")
        await self._send("✏️ Редагувати")
        await self._send("Sunlu PETG")

        # Edit color
        await self._send("🌈 Колір")
        await self._send("🔵 Синій")
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["s_edit"]["color"], "#3B82F6")

        # Edit quantity
        await self._send("✏️ Редагувати")
        await self._send("Sunlu PETG")
        await self._send("📦 Кількість")
        await self._send("5 шт")
        spools = await self.app.storage.load_spools()
        self.assertEqual(spools["s_edit"]["quantity"], 5)


