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


if __name__ == "__main__":
    unittest.main()
