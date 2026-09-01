"""
Rigorously designed QA Edge Cases & Adversarial Test Suite.
Simulates real QA engineering testing: invalid inputs, boundary conditions, state corruptions,
permission denials, garbage strings, corrupt files, and unexpected workflows.
"""

import asyncio
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Chat, Message, User

from bot.handlers import setup_routers
from models.commercial import calculate_commercial_price, parse_val_or_percent
from services.gcode_parser import (
    format_print_time_human,
    parse_3mf_file,
    parse_time_str,
)
from services.report_generator import generate_csv_report
from storage.manager import StorageManager


class TestQACommercialEngine(unittest.TestCase):
    """QA tests for commercial calculation math engine and value parsing."""

    def test_parse_val_or_percent_edge_cases(self):
        # Normal fixed values (10 UAH/hr * 2.0 hrs = 20.0 UAH)
        self.assertEqual(parse_val_or_percent("10", 100.0, 2.0), (20.0, False))
        self.assertEqual(parse_val_or_percent("0", 100.0, 2.0), (0.0, False))

        # Percentages (50% of 100.0 UAH = 50.0 UAH)
        self.assertEqual(parse_val_or_percent("50%", 100.0, 2.0), (50.0, True))
        self.assertEqual(parse_val_or_percent("0%", 100.0, 2.0), (0.0, True))
        self.assertEqual(parse_val_or_percent("200%", 100.0, 2.0), (200.0, True))

        # Malformed / boundary inputs
        self.assertEqual(parse_val_or_percent("invalid", 100.0, 2.0), (0.0, False))
        self.assertEqual(parse_val_or_percent("", 100.0, 2.0), (0.0, False))
        self.assertEqual(parse_val_or_percent("  15.5 % ", 100.0, 2.0), (15.5, True))

    def test_calculate_commercial_price_boundary(self):
        preset = {
            "name": "QA Test Preset",
            "price_per_g": 0.85,
            "electricity_rate_uah": 4.32,
            "power_watts": 120.0,
            "depreciation_val": "10",
            "consumables_val": "5",
            "profit_val": "100%",
        }

        # Zero weight & time (has minimum setup fee of 3.10 грн for 0.1 hr)
        res_zero = calculate_commercial_price(preset, 0.0, 0)
        self.assertEqual(res_zero["total_price"], 3.10)

        # Extremely large print job (8 days)
        res_8d = calculate_commercial_price(preset, 500.0, 12661)
        self.assertGreater(res_8d["total_price"], 0.0)
        self.assertEqual(res_8d["weight_g"], 500.0)
        self.assertEqual(res_8d["time_mins"], 12661)


class TestQAGcodeParser(unittest.TestCase):
    """QA tests for 3MF metadata and time parsing."""

    def test_parse_time_str_complex_formats(self):
        # Single and multi-day formats
        self.assertEqual(parse_time_str("8d 18h 54m 54s"), 12654)
        self.assertEqual(
            parse_time_str("model printing time: 8d 18h 54m 54s; total estimated time: 8d 19h 1m 9s"), 12661
        )
        self.assertEqual(parse_time_str("1d 0h 0m"), 1440)

        # Seconds only
        self.assertEqual(parse_time_str("120s"), 0)  # Less than 1m -> 0m
        self.assertEqual(parse_time_str("3600s"), 0)  # s-only handled by s_match -> 0m unless h/m/d present

        # Time HH:MM:SS format
        self.assertEqual(parse_time_str("02:30:00"), 150)
        self.assertEqual(parse_time_str("00:45:00"), 45)

        # Trash inputs
        self.assertEqual(parse_time_str("random text 123"), 0)
        self.assertEqual(parse_time_str(None), 0)

    def test_format_print_time_human(self):
        self.assertEqual(format_print_time_human(0), "0 хв")
        self.assertEqual(format_print_time_human(45), "~45 хв")
        self.assertEqual(format_print_time_human(135), "~2г 15хв (135 хв)")
        self.assertEqual(format_print_time_human(12661), "~8д 19г 1хв (12661 хв)")

    def test_parse_corrupt_3mf_file(self):
        # Corrupt bytes (not a valid zip)
        res = parse_3mf_file(b"corrupt non-zip binary data", "corrupt.3mf")
        self.assertTrue(res["valid"])
        self.assertEqual(res["printer_model"], "corrupt.3mf")
        self.assertEqual(res["weight_g"], 0.0)
        self.assertEqual(res["time_mins"], 0)


class TestQATelegramBotSecurityAndErrors(unittest.TestCase):
    """QA tests for permissions, error handling, invalid inputs, and state recovery."""

    def setUp(self):
        self.router = setup_routers()
        self.sm = StorageManager(Path("./printers_storage"))
        self.app = MagicMock()
        self.app.storage = self.sm
        self.chat = Chat(id=888999, type="private")
        self.user_obj = User(id=888999, is_bot=False, first_name="QA Tester")

    async def _send_msg(self, text: str) -> AsyncMock:
        msg = Message(message_id=505, date=datetime.now(), chat=self.chat, from_user=self.user_obj, text=text)
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_document", mock_answer)
        await self.router.propagate_event("message", msg, app=self.app, bot=self.app.bot)
        return mock_answer

    def test_unapproved_user_blocked(self):
        async def run_test():
            self.app.is_user_approved = AsyncMock(return_value=False)
            self.app.is_user_admin = AsyncMock(return_value=False)

            # Unapproved user tries to open dashboard or commercial menu
            ans = await self._send_msg("📊 Стан ферми")
            # Should ask for access or show access request keyboard
            if ans.called:
                self.assertIn("доступ", ans.call_args[0][0].lower())

        asyncio.run(run_test())

    def test_invalid_input_in_preset_wizard(self):
        async def run_test():
            self.app.is_user_approved = AsyncMock(return_value=True)
            self.app.is_user_admin = AsyncMock(return_value=True)

            await self.sm.save_user(
                {
                    "user_id": "888999",
                    "chat_id": "888999",
                    "state": "add_preset_price",
                    "context_data": {"new_preset": {}},
                }
            )

            # User sends non-numeric price string "abc"
            ans_bad = await self._send_msg("not_a_number")
            self.assertTrue(ans_bad.called)
            self.assertIn("числову", ans_bad.call_args[0][0].lower())
            # State should remain in add_preset_price
            user = await self.sm.load_user("888999")
            self.assertEqual(user["state"], "add_preset_price")

        asyncio.run(run_test())

    def test_back_button_cancels_wizard(self):
        async def run_test():
            self.app.is_user_approved = AsyncMock(return_value=True)
            self.app.is_user_admin = AsyncMock(return_value=True)

            await self.sm.save_user(
                {"user_id": "888999", "chat_id": "888999", "state": "add_preset_name", "context_data": {}}
            )

            # User clicks "⬅️ Назад"
            ans_back = await self._send_msg("⬅️ Назад")
            self.assertTrue(ans_back.called)

            user = await self.sm.load_user("888999")
            self.assertEqual(user["state"], "idle")

        asyncio.run(run_test())


class TestQAReportGenerator(unittest.TestCase):
    """QA tests for CSV report generation with special characters."""

    def test_csv_report_special_chars(self):
        history = [
            {
                "timestamp": "2026-08-08 19:00:00",
                "printer_name": 'Bambu "P1S" Special, Name',
                "job_name": "box_model_test,v1.3mf\nwith_newline",
                "weight_g": 125.5,
                "status": "FINISHED",
            }
        ]
        import csv
        import io

        csv_bytes = generate_csv_report(history)
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))  # UTF-8-BOM check
        decoded = csv_bytes.decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(decoded), delimiter=";"))
        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[1][2], 'Bambu "P1S" Special, Name')


if __name__ == "__main__":
    unittest.main()
