"""
Unit tests for OrcaSlicer hook script.
"""

import unittest
from pathlib import Path

from orca_hook import BASE_DIR, LOG_FILE, WEIGHT_CACHE


class TestOrcaHook(unittest.TestCase):
    def test_dynamic_paths(self):
        expected_base = Path(__file__).resolve().parent.parent
        self.assertEqual(BASE_DIR, expected_base)
        self.assertEqual(LOG_FILE, expected_base / "logs" / "orca_hook.log")
        self.assertEqual(WEIGHT_CACHE, expected_base / "printers_storage" / "last_sliced_weight.json")


if __name__ == "__main__":
    unittest.main()
