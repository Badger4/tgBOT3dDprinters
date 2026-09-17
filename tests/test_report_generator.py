import io
import unittest
from types import SimpleNamespace

from services.report_generator import (
    generate_combined_warehouse_pdf_report,
    generate_history_pdf_report,
    generate_movements_pdf_report,
    generate_parts_pdf_report,
    generate_spools_pdf_report,
    generate_warehouse_pdf_report,
)


class TestReportGenerator(unittest.TestCase):

    def test_generate_history_pdf_report(self):
        from services.report_generator import generate_history_pdf_report
        sample_history = [
            {
                "timestamp": 1700000000,
                "printer_name": "Bambu Lab P1S",
                "subtask_name": "Box_PLA_1h.3mf",
                "filament_type": "PLA",
                "weight_g": 45.5,
                "note": "Успішно",
            },
        ]
        pdf_bytes = generate_history_pdf_report(sample_history)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_spools_pdf_report(self):
        from services.report_generator import generate_spools_pdf_report
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
            }
        }
        pdf_bytes = generate_spools_pdf_report(spools)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_parts_pdf_report(self):
        from services.report_generator import generate_parts_pdf_report
        parts = {
            "part_1": {
                "id": "part_1",
                "name": "Gear Wheel",
                "printer_model": "Bambu Lab A1 mini",
                "filament_type": "PLA",
                "weight_g": 25.0,
                "price": 50.0,
                "count": 5,
            }
        }
        pdf_bytes = generate_parts_pdf_report(parts)
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_combined_and_movements_pdf_report(self):
        from services.report_generator import (
            generate_combined_warehouse_pdf_report,
            generate_movements_pdf_report,
            generate_warehouse_pdf_report,
        )
        spools = {"s1": {"name": "Test Spool", "remaining_grams": 500.0, "price_per_kg": 600.0}}
        parts = {"p1": {"name": "Test Part", "price": 100.0, "count": 2}}

        pdf_comb = generate_combined_warehouse_pdf_report(spools, parts)
        self.assertTrue(pdf_comb.startswith(b"%PDF"))

        pdf_ware = generate_warehouse_pdf_report(spools, parts, report_type="all")
        self.assertTrue(pdf_ware.startswith(b"%PDF"))

        movs = [
            {
                "id": "mov_1",
                "datetime": "2026-09-03 10:00:00",
                "spool_id": "s1",
                "spool_name": "Test Spool",
                "action": "Deduction",
                "weight_change_g": -50.0,
                "prev_weight_g": 550.0,
                "new_weight_g": 500.0,
                "reason": "Print",
                "user": "System",
            }
        ]
        pdf_movs = generate_movements_pdf_report(movs)
        self.assertTrue(pdf_movs.startswith(b"%PDF"))

    def test_generate_commercial_pdf_reports(self):
        from services.report_generator import (
            generate_commercial_calc_pdf,
            generate_commercial_pdf_report,
        )
        presets = {
            "p1": {
                "id": "p1",
                "name": "Standard PLA",
                "price_per_g": 0.85,
                "electricity_rate_uah": 4.32,
                "power_watts": 120.0,
                "depreciation_val": "10",
                "consumables_val": "5",
                "profit_val": "100%",
            }
        }
        pdf_report = generate_commercial_pdf_report(presets, lang="uk")
        self.assertTrue(pdf_report.startswith(b"%PDF"))
        self.assertTrue(len(pdf_report) > 1000)

        calc = {
            "preset_name": "Standard PLA",
            "weight_g": 100.0,
            "time_mins": 120,
            "time_hours": 2.0,
            "filament_cost": 85.0,
            "electricity_cost": 1.04,
            "depreciation_cost": 20.0,
            "depreciation_str": "10 грн/год",
            "consumables_cost": 10.0,
            "consumables_str": "5 грн/год",
            "profit_cost": 116.04,
            "profit_str": "+100%",
            "total_price": 232.08,
        }
        pdf_calc = generate_commercial_calc_pdf(calc, lang="uk")
        self.assertTrue(pdf_calc.startswith(b"%PDF"))
        self.assertTrue(len(pdf_calc) > 1000)

    def test_option_b_warehouse_and_mounted_spools(self):
        from services.report_generator import (
            _format_slot_name,
            _resolve_printer_name,
            generate_spools_pdf_report,
            generate_warehouse_pdf_report,
        )

        # 1. Test slot and printer resolvers
        self.assertEqual(_format_slot_name("0"), "Слот A1 (AMS)")
        self.assertEqual(_format_slot_name("254"), "Слот VT (Зовнішній)")
        self.assertEqual(_format_slot_name("255"), "Слот VT (Зовнішній)")
        self.assertEqual(_format_slot_name("custom_slot"), "Слот custom_slot")
        self.assertEqual(_format_slot_name(None), "Невідомий слот")

        printers = {
            "p_p1s": SimpleNamespace(id="p_p1s", name="Bambu Lab P1S"),
            "p_a1m": {"id": "p_a1m", "name": "A1 mini"},
        }
        self.assertEqual(_resolve_printer_name("p_p1s", printers), "Bambu Lab P1S")
        self.assertEqual(_resolve_printer_name("p_a1m", printers), "A1 mini")
        self.assertEqual(_resolve_printer_name("unknown_p", printers), "Принтер unknown_p")
        self.assertEqual(_resolve_printer_name(None, printers), "Невідомий принтер")

        # 2. Test Spools PDF generation with TPU 95A mounted and PLA on warehouse
        spools = {
            "s_wh": {
                "id": "s_wh",
                "name": "Eryone PLA White",
                "type": "PLA",
                "color": "Білий",
                "initial_grams": 1000.0,
                "remaining_grams": 900.0,
                "price_per_kg": 700.0,
                "quantity": 1,
                "assigned_printer_id": None,
                "assigned_slot_key": None,
            },
            "s_tpu": {
                "id": "s_tpu",
                "name": "Bambu TPU 95A HF",
                "type": "TPU",
                "color": "Чорний",
                "initial_grams": 1000.0,
                "remaining_grams": 850.0,
                "price_per_kg": 1200.0,
                "quantity": 1,
                "assigned_printer_id": "p_p1s",
                "assigned_slot_key": "254",
            },
        }

        # Generate Option B PDF
        pdf_bytes = generate_spools_pdf_report(spools, printers=printers)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertTrue(len(pdf_bytes) > 1000)

        # Test delegating via generate_warehouse_pdf_report with printers
        pdf_ware = generate_warehouse_pdf_report(spools, report_type="spools", printers=printers)
        self.assertTrue(pdf_ware.startswith(b"%PDF"))
        self.assertTrue(len(pdf_ware) > 1000)

    def test_empty_spools_pdf_report(self):
        from services.report_generator import generate_spools_pdf_report

        empty_pdf = generate_spools_pdf_report({})
        self.assertTrue(empty_pdf.startswith(b"%PDF"))
        self.assertTrue(len(empty_pdf) > 1000)


if __name__ == "__main__":
    unittest.main()
