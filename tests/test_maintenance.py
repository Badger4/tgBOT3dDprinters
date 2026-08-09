import unittest
from pathlib import Path
from storage.manager import StorageManager
from models.printer import BambuPrinter

class TestMaintenanceTracking(unittest.TestCase):
    def test_record_print_hours_and_reset(self):
        sm = StorageManager(Path("./printers_storage"))
        config = {
            "id": "test_maint_p1",
            "name": "Test Printer",
            "total_print_hours": 10.0,
            "maintenance_hours_counter": 95.0,
            "maintenance_interval_hours": 100
        }
        p = BambuPrinter(config, sm)
        self.assertEqual(p.total_print_hours, 10.0)
        self.assertEqual(p.maintenance_hours_counter, 95.0)

        # Record 10 hours print
        p.record_print_hours(10.0)
        self.assertEqual(p.total_print_hours, 20.0)
        self.assertEqual(p.maintenance_hours_counter, 105.0)
        self.assertTrue(p.maintenance_hours_counter >= p.maintenance_interval_hours)

        # Reset counter
        p.reset_maintenance_counter()
        self.assertEqual(p.maintenance_hours_counter, 0.0)
        self.assertEqual(p.total_print_hours, 20.0)

if __name__ == "__main__":
    unittest.main()
