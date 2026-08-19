"""
Unit tests for HMS error decoder service (services/hms_resolver.py).
"""

import unittest

from services.hms_resolver import decode_hms_entry, format_hms_errors


class TestHMSResolver(unittest.TestCase):
    def test_decode_hms_dict(self):
        # Code for filament jam: HMS_0300_0800_0001_0001
        entry = {"code": 0x03000800, "attr": 0x00010001}
        decoded = decode_hms_entry(entry)
        self.assertIn("HMS_0300_0800_0001_0001", decoded)
        self.assertIn("Застрягання нитки", decoded)

    def test_decode_dash_format(self):
        decoded = decode_hms_entry("0300-0100-0001-0003")
        self.assertIn("HMS_0300_0100_0001_0003", decoded)
        self.assertIn("Помилка датчика вирівнювання столу", decoded)

    def test_tier_fallback(self):
        # Tier 2: sub-prefix match HMS_0500_0100
        decoded_sub = decode_hms_entry("HMS_0500_0100_9999_9999")
        self.assertIn("Помилка мотора подачі нитки AMS", decoded_sub)

        # Tier 3: main category match HMS_0700
        decoded_main = decode_hms_entry("HMS_0700_9999_8888_7777")
        self.assertIn("Помилка сенсора Micro Lidar", decoded_main)

    def test_format_hms_errors(self):
        hms_list = [
            {"code": 0x03000800, "attr": 0x00010001},
            {"code": 0x03000A00, "attr": 0x00010001},
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
