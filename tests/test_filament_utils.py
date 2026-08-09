"""
Unit tests for filament_utils and AMSSlot/GCodeState enums.
"""
import unittest
from models.enums import AMSSlot, GCodeState
from utils.filament_utils import parse_slot_key_from_text, extract_filament_type_from_name

class TestFilamentUtils(unittest.TestCase):
    def test_parse_slot_key(self):
        self.assertEqual(parse_slot_key_from_text("Slot 1"), AMSSlot.A1.value)
        self.assertEqual(parse_slot_key_from_text("A2"), AMSSlot.A2.value)
        self.assertEqual(parse_slot_key_from_text("A3"), AMSSlot.A3.value)
        self.assertEqual(parse_slot_key_from_text("A4"), AMSSlot.A4.value)
        self.assertEqual(parse_slot_key_from_text("зовнішній"), AMSSlot.EXTERNAL.value)
        self.assertEqual(parse_slot_key_from_text("vt"), AMSSlot.EXTERNAL.value)

    def test_extract_filament_type(self):
        self.assertEqual(extract_filament_type_from_name("box_PLA_red.gcode"), "PLA")
        self.assertEqual(extract_filament_type_from_name("gear_PETG-CF.3mf"), "PETG-CF")
        self.assertEqual(extract_filament_type_from_name("custom_material"), "custom_material")

if __name__ == "__main__":
    unittest.main()
