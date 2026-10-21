"""
Unit tests for i18n module (utils/i18n.py).
"""

import unittest

from utils.i18n import get_button_variants, get_user_lang, t


class TestI18n(unittest.TestCase):
    def test_translation_uk(self):
        self.assertEqual(t("btn_warehouse", "uk"), "🧵 Філамент")
        self.assertEqual(t("btn_printers", "uk"), "🖨️ Принтери")

    def test_button_variants(self):
        vars_fil = get_button_variants("btn_warehouse", extra=["📦 Склад"])
        self.assertIn("🧵 Філамент", vars_fil)
        self.assertIn("філамент", vars_fil)
        self.assertIn("📦 Warehouse", vars_fil)
        self.assertIn("warehouse", vars_fil)
        self.assertIn("📦 Склад", vars_fil)
        self.assertIn("склад", vars_fil)

    def test_translation_en(self):
        self.assertEqual(t("btn_warehouse", "en"), "📦 Warehouse")
        self.assertEqual(t("btn_printers", "en"), "🖨️ Printers")

    def test_fallback(self):
        self.assertEqual(t("non_existent_key", "en"), "non_existent_key")

    def test_get_user_lang(self):
        self.assertEqual(get_user_lang({"language": "en"}), "en")
        self.assertEqual(get_user_lang({"language": "uk"}), "uk")
        self.assertEqual(get_user_lang(None), "uk")


if __name__ == "__main__":
    unittest.main()
