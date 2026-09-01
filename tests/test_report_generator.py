import csv
import io
import unittest
from types import SimpleNamespace

from services.report_generator import (
    generate_csv_report,
    generate_parts_csv_report,
    generate_spools_csv_report,
    generate_warehouse_csv_report,
)


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
            },
            {
                "timestamp": "2026-08-27 10:00:00",
                "printer_name": "Bambu Lab A1 mini",
                "subtask_name": "Gear.3mf",
                "filament_type": "PETG",
                "weight_g": 12.0,
                "note": "Помилка",
            },
        ]
        csv_bytes = generate_csv_report(sample_history)
        self.assertTrue(len(csv_bytes) > 0)
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        # 1 sep= header + 1 table header + 2 data rows = 4 rows
        self.assertEqual(len(rows), 4)

    def test_generate_spools_csv_report_dict(self):
        spools = {
            "spool_1": {
                "id": "spool_1",
                "name": "Black PLA",
                "type": "PLA",
                "color": "#000000",
                "initial_grams": 1000,
                "remaining_grams": 750,
                "price_per_kg": 650.0,
                "quantity": 2,
                "assigned_slot_key": "AMS1_Slot1",
            },
            "spool_2": {
                "name": "White PETG",
            },
        }
        csv_bytes = generate_spools_csv_report(spools)
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        # 1 sep= header + 1 table header + 2 spools + 1 empty + 1 summary = 6 rows
        self.assertEqual(len(rows), 6)
        self.assertIn("Black PLA", rows[2][1])
        self.assertIn("Прив'язаний: Слот AMS1_Slot1", rows[2][8])
        self.assertIn("На складі", rows[3][8])
        self.assertEqual(rows[-1][0], "ВАРТІСТЬ СКЛАДУ")

    def test_generate_spools_csv_report_objects(self):
        spool_obj = SimpleNamespace(
            id="spool_obj_1",
            name="Red ABS",
            type="ABS",
            color="Red",
            initial_grams=1000.0,
            remaining_grams=900.0,
            price_per_kg=700.0,
            quantity=1,
            assigned_slot_key=None,
        )
        csv_bytes = generate_spools_csv_report({"spool_obj_1": spool_obj})
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        # 1 sep= header + 1 table header + 1 spool + 1 empty + 1 summary = 5 rows
        self.assertEqual(len(rows), 5)
        self.assertIn("Red ABS", rows[2][1])
        self.assertEqual(rows[-1][0], "ВАРТІСТЬ СКЛАДУ")

    def test_generate_parts_csv_report(self):
        parts = {
            "part_1": {
                "id": "part_1",
                "name": "Gear Wheel",
                "printer_model": "Bambu Lab A1 mini",
                "filament_type": "PLA",
                "weight_g": 25.0,
                "price": 50.0,
                "count": 5,
            },
            "part_2": {},
        }
        csv_bytes = generate_parts_csv_report(parts)
        text = csv_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text), delimiter=";")
        rows = list(reader)
        # 1 sep= header + 1 table header + 2 parts + 1 empty + 1 summary = 6 rows
        self.assertEqual(len(rows), 6)
        self.assertIn("Gear Wheel", rows[2][1])
        self.assertIn("ВАРТІСТЬ СКЛАДУ ДЕТАЛЕЙ", rows[5][0])

    def test_generate_warehouse_csv_report(self):
        spools = {"s1": {"name": "Test Spool"}}
        parts = {"p1": {"name": "Test Part"}}

        res_spools = generate_warehouse_csv_report(spools, parts, report_type="spools")
        self.assertIn("Test Spool", res_spools.decode("utf-8-sig"))

        res_parts = generate_warehouse_csv_report(spools, parts, report_type="parts")
        self.assertIn("Test Part", res_parts.decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
