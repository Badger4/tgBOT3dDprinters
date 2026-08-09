"""
Unit tests for gcode_parser services.
"""
import unittest
from services.gcode_parser import parse_time_str, resolve_model_name, check_compatibility

class TestGcodeParser(unittest.TestCase):
    def test_parse_time_str(self):
        self.assertEqual(parse_time_str("1h 30m"), 90)
        self.assertEqual(parse_time_str("45m"), 45)
        self.assertEqual(parse_time_str("01:15:00"), 75)
        self.assertEqual(parse_time_str("8d 18h 54m 54s"), 8 * 1440 + 18 * 60 + 54) # 12654
        self.assertEqual(parse_time_str("model printing time: 8d 18h 54m 54s; total estimated time: 8d 19h 1m 9s"), 8 * 1440 + 19 * 60 + 1) # 12661
        self.assertEqual(parse_time_str(""), 0)

    def test_resolve_model_name(self):
        self.assertEqual(resolve_model_name("n2s"), "Bambu Lab A1 mini")
        self.assertEqual(resolve_model_name("n1"), "Bambu Lab A1")
        self.assertEqual(resolve_model_name("c12"), "Bambu Lab P1S")
        self.assertEqual(resolve_model_name("c10"), "Bambu Lab X1 Carbon")
        self.assertEqual(resolve_model_name("Bambu ABS @BBL A1"), "Bambu Lab A1")
        self.assertEqual(resolve_model_name("Bambu ABS @BBL A1M"), "Bambu Lab A1 mini")
        self.assertEqual(resolve_model_name("Unknown"), "Unknown")

    def test_check_compatibility(self):
        # Same printer model
        res1 = check_compatibility("Bambu Lab A1", "PLA", "Bambu Lab A1")
        self.assertTrue(res1["compatible"])
        self.assertEqual(res1["level"], "OK")

        # Incompatible model (P1S gcode on A1 mini)
        res2 = check_compatibility("Bambu Lab P1S", "PLA", "Bambu Lab A1 mini")
        self.assertFalse(res2["compatible"])
        self.assertEqual(res2["level"], "BLOCK")

        # A1 mini gcode on A1 printer -> incompatible in strict mode
        res3 = check_compatibility("Bambu Lab A1 mini", "ABS", "Bambu Lab A1")
        self.assertFalse(res3["compatible"])
        self.assertEqual(res3["level"], "BLOCK")

if __name__ == "__main__":
    unittest.main()
