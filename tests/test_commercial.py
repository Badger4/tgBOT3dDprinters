import unittest

from models.commercial import calculate_commercial_price, parse_val_or_percent


class TestCommercialCalculator(unittest.TestCase):
    def test_parse_val_or_percent(self):
        val, is_pct = parse_val_or_percent("50%", 200.0, 2.0)
        self.assertEqual(val, 100.0)
        self.assertTrue(is_pct)

        val, is_pct = parse_val_or_percent("10", 200.0, 2.0)
        self.assertEqual(val, 20.0)  # 10 грн/год * 2 год = 20 грн
        self.assertFalse(is_pct)

    def test_calculate_commercial_price(self):
        preset = {
            "name": "Стандарт PLA",
            "price_per_g": 0.85,
            "electricity_rate_uah": 4.0,
            "power_watts": 250.0,  # 0.25 kW * 2h = 0.5 kWh -> 2.0 грн
            "depreciation_val": "10",  # 10 грн/г * 2h = 20 грн
            "consumables_val": "5",  # 5 грн/г * 2h = 10 грн
            "profit_val": "100%",  # +100% margin
        }
        res = calculate_commercial_price(preset, weight_g=100.0, time_mins=120)
        self.assertEqual(res["weight_g"], 100.0)
        self.assertEqual(res["filament_cost"], 85.0)  # 100g * 0.85 = 85 грн
        self.assertEqual(res["electricity_cost"], 2.0)  # 0.5 kWh * 4.0 = 2 грн
        self.assertEqual(res["direct_cost"], 87.0)
        self.assertEqual(res["depreciation_cost"], 20.0)
        self.assertEqual(res["consumables_cost"], 10.0)
        self.assertEqual(res["cost_before_profit"], 117.0)  # 87 + 20 + 10 = 117
        self.assertEqual(res["profit_cost"], 117.0)  # 100% of 117 = 117 грн
        self.assertEqual(res["total_price"], 234.0)  # 117 + 117 = 234 грн

    def test_validate_val_or_percent(self):
        from models.commercial import validate_val_or_percent

        # Valid numeric
        ok, res = validate_val_or_percent("10")
        self.assertTrue(ok)
        self.assertEqual(res, "10")

        ok, res = validate_val_or_percent("15.5")
        self.assertTrue(ok)
        self.assertEqual(res, "15.5")

        ok, res = validate_val_or_percent("10,5")
        self.assertTrue(ok)
        self.assertEqual(res, "10.5")

        # Valid with units
        ok, res = validate_val_or_percent("10 грн/год")
        self.assertTrue(ok)
        self.assertEqual(res, "10")

        ok, res = validate_val_or_percent("15 грн")
        self.assertTrue(ok)
        self.assertEqual(res, "15")

        ok, res = validate_val_or_percent("20 uah")
        self.assertTrue(ok)
        self.assertEqual(res, "20")

        # Valid percentage
        ok, res = validate_val_or_percent("15%")
        self.assertTrue(ok)
        self.assertEqual(res, "15%")

        ok, res = validate_val_or_percent("+100%")
        self.assertTrue(ok)
        self.assertEqual(res, "100%")

        # Zero
        ok, res = validate_val_or_percent("0")
        self.assertTrue(ok)
        self.assertEqual(res, "0")

        # Invalid strings
        ok, res = validate_val_or_percent("abc")
        self.assertFalse(ok)
        self.assertIn("⚠️", res)

        ok, res = validate_val_or_percent("десять")
        self.assertFalse(ok)
        self.assertIn("⚠️", res)

        ok, res = validate_val_or_percent("")
        self.assertFalse(ok)

        ok, res = validate_val_or_percent("-10")
        self.assertFalse(ok)
        self.assertIn("від'ємним", res)

        ok, res = validate_val_or_percent("-15%")
        self.assertFalse(ok)

        ok, res = validate_val_or_percent("nan")
        self.assertFalse(ok)

        ok, res = validate_val_or_percent("inf")
        self.assertFalse(ok)

    def test_drugarnya_serial_mode_and_savings(self):
        preset = {"name": "Test Preset", "price_per_g": 0.85, "electricity_rate_uah": 4.32, "power_watts": 120.0}
        res = calculate_commercial_price(
            preset,
            weight_g=80.0,
            time_mins=120,
            mode="serial",
            serial_qty=10,
            serial_per_plate=2,
            prep_time_mins=20,
            serial_post_mins=5,
            labor_rate_uah=150.0,
            serial_pack_cost=10.0,
            margin_pct=100.0,
        )
        self.assertEqual(res["mode"], "serial")
        self.assertEqual(res["serial_qty"], 10)
        self.assertGreater(res["serial_saving"], 0)
        self.assertIn("total_batch_price", res)
        self.assertIn("verdict_status", res)
        self.assertIn("verdict_main", res)

    def test_drugarnya_test_prototype_mode(self):
        preset = {"name": "Test Preset", "price_per_g": 0.85, "electricity_rate_uah": 4.32, "power_watts": 120.0}
        res_single = calculate_commercial_price(preset, weight_g=80.0, time_mins=120, prep_time_mins=20, labor_rate_uah=150.0)
        res_test = calculate_commercial_price(preset, weight_g=80.0, time_mins=120, mode="test", prep_time_mins=20, labor_rate_uah=150.0)
        # Test mode should include extra labor risk allowance
        self.assertGreater(res_test["cost_per_unit"], res_single["cost_per_unit"])
        self.assertEqual(res_test["mode"], "test")

    def test_drugarnya_day_night_tariff(self):
        preset = {"name": "Test Preset", "price_per_g": 0.85, "power_watts": 1000.0} # 1 kW
        res = calculate_commercial_price(
            preset,
            weight_g=10.0,
            time_mins=120, # 2 hours
            tariff_mode="daynight",
            elec_day_rate=4.0,
            elec_night_rate=2.0,
            elec_day_hours=1.0,
            elec_night_hours=1.0,
        )
        # 1 kW * (1h * 4 + 1h * 2) = 6 грн
        self.assertEqual(res["electricity_cost"], 6.0)


if __name__ == "__main__":
    unittest.main()

