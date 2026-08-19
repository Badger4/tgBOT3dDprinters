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

    def test_decode_unknown_hms_code(self):
        entry = {"code": 0x99999999, "attr": 0x88888888}
        decoded = decode_hms_entry(entry)
        self.assertEqual(decoded, "HMS_9999_9999_8888_8888")

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
