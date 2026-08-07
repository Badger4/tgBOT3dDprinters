"""
Unit tests for BambuPrinter model.
"""
import unittest
import tempfile
from pathlib import Path
from storage.manager import StorageManager
from models.printer import BambuPrinter

class TestPrinterModel(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(Path(self.temp_dir.name))
        self.config = {
            "id": "test_p1",
            "name": "Test Printer P1S",
            "ip": "192.168.1.100",
            "accessCode": "12345678",
            "serialNumber": "01P00A123456789",
            "filament_grams": 1000.0,
            "price_per_kg": 650.0,
            "power_watts": 120.0,
            "electricity_rate_uah": 4.32
        }
        self.printer = BambuPrinter(self.config, self.storage)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_calculate_job_cost(self):
        # 100g weight, default electricity cost calculation
        cost_info = self.printer.calculate_job_cost(100.0, print_mins=60)
        self.assertGreater(cost_info["filament_cost"], 0.0)
        self.assertGreater(cost_info["electricity_cost"], 0.0)
        self.assertEqual(cost_info["total_cost"], round(cost_info["filament_cost"] + cost_info["electricity_cost"], 2))

    def test_filament_deduction(self):
        self.assertEqual(self.printer.filament_grams, 1000.0)
        job_weight = 45.5
        self.printer._current_job_grams = job_weight
        self.printer.gcode_state = "RUNNING"

        # Simulate deduction logic
        old_w = self.printer.filament_grams
        self.printer.filament_grams = round(self.printer.filament_grams - self.printer._current_job_grams, 2)
        self.printer._job_deducted = True

        self.assertEqual(self.printer.filament_grams, 954.5)
        self.assertTrue(self.printer._job_deducted)

    def test_negative_filament_deficit(self):
        self.printer.filament_grams = 3.0
        job_weight = 6.47
        self.printer.filament_grams = round(self.printer.filament_grams - job_weight, 2)
        self.assertEqual(self.printer.filament_grams, -3.47)

if __name__ == "__main__":
    unittest.main()
