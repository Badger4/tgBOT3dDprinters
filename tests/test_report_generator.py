import csv
import io
import unittest

from services.report_generator import generate_csv_report


class TestReportGenerator(unittest.TestCase):
    def test_generate_csv_report(self):
        sample_history = [
            {
                "timestamp": 1700000000,
                "printer_name": "Bambu Lab P1S",
                "subtask_name": "Box_PLA_1h.3mf",
                "filament_type": "PLA",
                "weight_g": 45.5,
                "cost_uah": 32.0,
                "note": "Успішно",
            }
        ]
        csv_bytes = generate_csv_report(sample_history)
        self.assertTrue(len(csv_bytes) > 0)
        # Verify UTF-8-BOM
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][2], "Bambu Lab P1S")


if __name__ == "__main__":
    unittest.main()
