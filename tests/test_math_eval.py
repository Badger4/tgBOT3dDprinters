"""
Unit tests for safe_eval_math utility.
"""
import unittest
from utils.math_eval import safe_eval_math

class TestMathEval(unittest.TestCase):
    def test_basic_addition(self):
        self.assertEqual(safe_eval_math("100 + 200"), 300.0)

    def test_subtraction_with_units(self):
        self.assertEqual(safe_eval_math("1000 - 15.5g"), 984.5)
        self.assertEqual(safe_eval_math("1000g - 25г"), 975.0)

    def test_multiplication_with_currency(self):
        self.assertEqual(safe_eval_math("650 * 0.5 грн"), 325.0)

    def test_division_and_floats(self):
        self.assertEqual(safe_eval_math("100 / 4"), 25.0)
        self.assertEqual(safe_eval_math("10,5 + 5,5"), 16.0)

    def test_invalid_expressions(self):
        self.assertIsNone(safe_eval_math("invalid_expr"))
        self.assertIsNone(safe_eval_math("__import__('os').system('dir')"))
        self.assertIsNone(safe_eval_math(""))

if __name__ == "__main__":
    unittest.main()
