"""
Unit tests for HMS error decoder service (services/hms_resolver.py).
"""

import unittest

from services.hms_resolver import decode_hms_entry, decode_print_error, format_hms_errors


class TestHMSResolver(unittest.TestCase):
    def test_decode_hms_dict_standard_order(self):
        # Real Bambu Lab MQTT: attr is module (0x07FF2000), code is error index (0x00020004)
        entry = {"attr": 0x07FF2000, "code": 0x00020004}
        decoded = decode_hms_entry(entry)
        self.assertIn("07FF-2000-0002-0004", decoded)
        self.assertIn("зовнішній філамент", decoded)
        self.assertNotIn("вентилятор", decoded.lower())
        self.assertNotIn("каретки", decoded.lower())

    def test_decode_hms_dict_legacy_swapped_order(self):
        # Code for filament jam: category in code, attr has sub-index
        entry = {"code": 0x03000800, "attr": 0x00010001}
        decoded = decode_hms_entry(entry)
        self.assertIn("0300-0800-0001-0001", decoded)
        self.assertIn("Застрягання нитки", decoded)

    def test_decode_dash_format(self):
        decoded = decode_hms_entry("0300-0100-0001-0003")
        self.assertIn("0300-0100-0001-0003", decoded)
        self.assertIn("Помилка датчика вирівнювання столу", decoded)

    def test_tier_fallback(self):
        # Tier 2: sub-prefix match HMS_0500_0100
        decoded_sub = decode_hms_entry("HMS_0500_0100_9999_9999")
        self.assertIn("Помилка мотора подачі нитки AMS", decoded_sub)

        # Tier 3: main category match HMS_0700
        decoded_main = decode_hms_entry("HMS_0700_9999_8888_7777")
        self.assertIn("Помилка сенсора Micro Lidar", decoded_main)

    def test_decode_print_error(self):
        # 134201347 = 0x07FFC003 (Pull external filament prompt)
        res1 = decode_print_error(134201347)
        self.assertIsNotNone(res1)
        self.assertIn("зовнішньої котушки", res1)

        res2 = decode_print_error("134201347")
        self.assertEqual(res1, res2)

        res3 = decode_print_error("0x07FFC003")
        self.assertEqual(res1, res3)

        # Unknown or zero codes
        self.assertIsNone(decode_print_error(0))
        self.assertIsNone(decode_print_error("0"))
        self.assertIsNone(decode_print_error(None))
        self.assertIsNone(decode_print_error(""))

    def test_format_hms_errors(self):
        hms_list = [
            {"attr": 0x03000800, "code": 0x00010001},
            {"attr": 0x03000A00, "code": 0x00010001},
        ]
        formatted = format_hms_errors(hms_list)
        self.assertEqual(len(formatted), 2)
        self.assertIn("Застрягання нитки", formatted[0])
        self.assertIn("спагеті", formatted[1])

    def test_format_empty_hms_errors(self):
        self.assertEqual(format_hms_errors([]), [])
        self.assertEqual(format_hms_errors(None), [])


if __name__ == "__main__":
    unittest.main()
