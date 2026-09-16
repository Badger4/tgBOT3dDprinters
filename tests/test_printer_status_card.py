import unittest
from unittest.mock import MagicMock
from models.printer import BambuPrinter
from bot.handlers.printers.view import format_remaining_time, build_printer_status_card


class TestPrinterStatusCard(unittest.TestCase):
    def setUp(self):
        self.printer_cfg = {
            "id": "p1s_test",
            "name": "Bambu Lab P1S",
            "ip": "192.168.1.100",
            "accessCode": "12345678",
            "serialNumber": "01P00A123456789",
            "printer_model": "P1S",
            "filament_grams": 442.21,
            "filament_type": "PETG",
        }
        self.printer = BambuPrinter(self.printer_cfg, storage=MagicMock())
        self.printer.is_mqtt_connected = True

    def test_format_remaining_time(self):
        # Ukrainian
        self.assertEqual(format_remaining_time(0, is_en=False), "")
        self.assertEqual(format_remaining_time(-5, is_en=False), "")
        self.assertEqual(format_remaining_time(45, is_en=False), "45 хв")
        self.assertEqual(format_remaining_time(60, is_en=False), "1 год")
        self.assertEqual(format_remaining_time(125, is_en=False), "2 год 5 хв")

        # English
        self.assertEqual(format_remaining_time(45, is_en=True), "45 min")
        self.assertEqual(format_remaining_time(60, is_en=True), "1h")
        self.assertEqual(format_remaining_time(125, is_en=True), "2h 5m")

    def test_status_card_idle(self):
        self.printer.gcode_state = "IDLE"
        card_uk = build_printer_status_card(self.printer, is_en=False)
        self.assertIn("Стан принтера: Bambu Lab P1S", card_uk)
        self.assertIn("Онлайн", card_uk)

    def test_status_card_running_shows_remaining_time_and_progress(self):
        self.printer.gcode_state = "RUNNING"
        self.printer.subtask_name = "bracket.gcode.3mf"
        self.printer.mc_percent = 65
        self.printer.mc_remaining_time = 85  # 1h 25m
        self.printer.layer_num = 130
        self.printer.total_layer_num = 200

        # Ukrainian
        card_uk = build_printer_status_card(self.printer, is_en=False)
        self.assertIn("Друкує (~1 год 25 хв)", card_uk)
        self.assertIn("Завдання:</b> <code>bracket.gcode.3mf</code>", card_uk)
        self.assertIn("Прогрес:</b> <code>65%</code>", card_uk)
        self.assertIn("Залишилось друкувати:</b> <code>~1 год 25 хв (85 хв)</code>", card_uk)
        self.assertIn("Шар:</b> <code>130 / 200</code>", card_uk)

        # English
        card_en = build_printer_status_card(self.printer, is_en=True)
        self.assertIn("Printing (~1h 25m)", card_en)
        self.assertIn("Job:</b> <code>bracket.gcode.3mf</code>", card_en)
        self.assertIn("Progress:</b> <code>65%</code>", card_en)
        self.assertIn("Time Remaining:</b> <code>~1h 25m (85 min)</code>", card_en)
        self.assertIn("Layer:</b> <code>130 / 200</code>", card_en)


if __name__ == "__main__":
    unittest.main()
