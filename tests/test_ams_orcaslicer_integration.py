import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from bot.handlers.filament.mount import parse_slot_key_from_text as parse_mount_slot
from bot.handlers.filament.view import handle_ams_slots
from bot.handlers.printers.view import build_printer_status_card
from bot.keyboards import get_ams_slots_keyboard
from models.printer import BambuPrinter
from utils.filament_utils import get_color_emoji, parse_slot_key_from_text as parse_util_slot


class TestAmsOrcaSlicerIntegration(unittest.TestCase):
    def setUp(self):
        self.printer_cfg = {
            "id": "x1c_ams_test",
            "name": "Bambu Lab X1C",
            "ip": "192.168.1.101",
            "accessCode": "87654321",
            "serialNumber": "00M00A123456789",
            "printer_model": "X1C",
            "has_ams": True,
            "ams_enabled": True,
            "ams_humidity_idx": 5,
            "ams_temp": 24.5,
            "ams_slots": {
                "0": 820.0,
                "1": 550.0,
                "2": 0.0,
                "3": 100.0,
                "254": 1000.0,
            },
            "ams_trays_info": {
                "0": {
                    "id": "0",
                    "empty": False,
                    "type": "PLA",
                    "sub_brands": "Basic",
                    "color": "#00AE42",
                    "remain": 82,
                },
                "1": {
                    "id": "1",
                    "empty": False,
                    "type": "PETG",
                    "sub_brands": "HF",
                    "color": "#FFFFFF",
                    "remain": 55,
                },
                "2": {
                    "id": "2",
                    "empty": True,
                    "type": "",
                    "color": "",
                    "remain": -1,
                },
                "3": {
                    "id": "3",
                    "empty": False,
                    "type": "ABS",
                    "sub_brands": "",
                    "color": "#1A1A1A",
                    "remain": 10,
                },
                "254": {
                    "id": "254",
                    "empty": False,
                    "type": "TPU",
                    "sub_brands": "95A",
                    "color": "#EF4444",
                    "remain": 100,
                },
            },
        }
        self.printer = BambuPrinter(self.printer_cfg, storage=MagicMock())
        self.printer.is_mqtt_connected = True
        self.printer.active_ams_tray = 0

    def test_status_card_orcaslicer_ams_display(self):
        # Ukrainian
        card_uk = build_printer_status_card(self.printer, is_en=False)
        self.assertIn("🌈 <b>Слоти AMS:</b>", card_uk)
        self.assertIn("A1:</b> PLA Basic — <b>82%</b> (820g) ⚡", card_uk)
        self.assertIn("A2:</b> PETG HF — <b>55%</b> (550g)", card_uk)
        self.assertIn("⚪ <b>A3:</b> <i>Порожньо</i>", card_uk)
        self.assertIn("A4:</b> ABS — <b>10%</b> (100g)", card_uk)
        self.assertIn("🧵 <b>VT:</b>", card_uk)
        self.assertIn("TPU 95A — <b>100%</b> (1000g)", card_uk)
        self.assertIn("💧 <b>Вологість AMS:</b> 🟢 5/5 (Ідеально сухо)", card_uk)
        self.assertIn("24.5°C", card_uk)

        # English
        card_en = build_printer_status_card(self.printer, is_en=True)
        self.assertIn("🌈 <b>AMS Slots:</b>", card_en)
        self.assertIn("A1:</b> PLA Basic — <b>82%</b> (820g) ⚡", card_en)
        self.assertIn("⚪ <b>A3:</b> <i>Empty</i>", card_en)
        self.assertIn("💧 <b>AMS Humidity:</b> 🟢 5/5 (Perfectly Dry)", card_en)

    def test_status_card_no_ams_shows_clean_vt(self):
        self.printer.ams_enabled = False
        self.printer.active_ams_tray = 254
        card_uk = build_printer_status_card(self.printer, is_en=False)
        self.assertNotIn("🌈 <b>Слоти AMS:</b>", card_uk)
        self.assertIn("🧵 <b>Філамент (VT):</b>", card_uk)
        self.assertIn("1000g", card_uk)

    def test_get_ams_slots_keyboard_layout_and_parsing(self):
        kb_uk = get_ams_slots_keyboard(self.printer, lang="uk")
        # 4 rows: [A1, A2], [A3, A4], [VT], [Back]
        self.assertEqual(len(kb_uk.keyboard), 4)
        self.assertEqual(len(kb_uk.keyboard[0]), 2)
        self.assertEqual(len(kb_uk.keyboard[1]), 2)
        self.assertEqual(len(kb_uk.keyboard[2]), 1)
        self.assertEqual(len(kb_uk.keyboard[3]), 1)

        btn_a1 = kb_uk.keyboard[0][0].text
        btn_a2 = kb_uk.keyboard[0][1].text
        btn_a3 = kb_uk.keyboard[1][0].text
        btn_a4 = kb_uk.keyboard[1][1].text
        btn_vt = kb_uk.keyboard[2][0].text

        # Content checks
        self.assertIn("A1:", btn_a1)
        self.assertIn("PLA", btn_a1)
        self.assertIn("82%", btn_a1)
        self.assertIn("⚡", btn_a1)  # Active slot

        self.assertIn("A2:", btn_a2)
        self.assertIn("PETG", btn_a2)
        self.assertIn("55%", btn_a2)
        self.assertNotIn("⚡", btn_a2)

        self.assertIn("A3:", btn_a3)
        self.assertIn("Порожньо", btn_a3)

        self.assertIn("A4:", btn_a4)
        self.assertIn("ABS", btn_a4)
        self.assertIn("10%", btn_a4)

        self.assertIn("VT:", btn_vt)
        self.assertIn("TPU", btn_vt)

        # Compatibility with parse_slot_key_from_text (both utils and mount versions)
        self.assertEqual(parse_util_slot(btn_a1), "0")
        self.assertEqual(parse_mount_slot(btn_a1), "0")

        self.assertEqual(parse_util_slot(btn_a2), "1")
        self.assertEqual(parse_mount_slot(btn_a2), "1")

        self.assertEqual(parse_util_slot(btn_a3), "2")
        self.assertEqual(parse_mount_slot(btn_a3), "2")

        self.assertEqual(parse_util_slot(btn_a4), "3")
        self.assertEqual(parse_mount_slot(btn_a4), "3")

        self.assertEqual(parse_util_slot(btn_vt), "254")
        self.assertEqual(parse_mount_slot(btn_vt), "254")

    def test_get_ams_slots_keyboard_en(self):
        kb_en = get_ams_slots_keyboard(self.printer, lang="en")
        btn_a3 = kb_en.keyboard[1][0].text
        self.assertIn("Empty", btn_a3)

    def test_get_ams_slots_keyboard_non_ams(self):
        self.printer.ams_enabled = False
        kb = get_ams_slots_keyboard(self.printer, lang="uk")
        self.assertEqual(len(kb.keyboard), 2)
        btn_vt = kb.keyboard[0][0].text
        self.assertIn("VT:", btn_vt)
        self.assertEqual(parse_mount_slot(btn_vt), "254")

    def test_handle_ams_slots_view(self):
        async def _test():
            msg = MagicMock()
            msg.chat.id = 12345
            msg.answer = AsyncMock()

            app = MagicMock()
            app.storage.load_user = AsyncMock(
                return_value={
                    "language": "uk",
                    "context_data": {"selected_printer_id": "x1c_ams_test"},
                }
            )
            app.printers = {"x1c_ams_test": self.printer}

            await handle_ams_slots(msg, app)

            self.assertTrue(msg.answer.called)
            sent_text = msg.answer.call_args[0][0]

            # Header & Nozzle feed
            self.assertIn("🌈 Модуль AMS — Bambu Lab X1C", sent_text)
            self.assertIn("🔥 <b>Подача в сопло:</b>", sent_text)
            self.assertIn("A1", sent_text)
            self.assertIn("⚡", sent_text)

            # Humidity
            self.assertIn("💧 <b>Вологість AMS:</b> 🟢 5/5", sent_text)

            # Progress bars
            self.assertIn("<code>████████░░</code> <b>82%</b> (820g)", sent_text)
            self.assertIn("<code>██████░░░░</code> <b>55%</b> (550g)", sent_text)
            self.assertIn("Слот A3:</b> <i>Порожньо</i>", sent_text)
            self.assertIn("<code>█░░░░░░░░░</code> <b>10%</b> (100g)", sent_text)
            self.assertIn("Слот VT (Зовнішній):", sent_text)

        asyncio.run(_test())

    def test_non_ams_printer_with_custom_weights_shows_only_vt(self):
        """Tests that a printer without AMS (e.g. A1 mini 2 with ams_exist_bits=0) shows ONLY 1 slot (VT) even if slot weights exist."""
        p_cfg = {
            "id": "a1_mini_test",
            "name": "Bambu Lab A1 mini 2",
            "ip": "192.168.1.2",
            "accessCode": "12345678",
            "serialNumber": "0309DA561100751",
            "printer_model": "A1 mini",
            "ams_exist_bits": "0",
            "has_ams": False,
            "filament_type": "TPU",
            "ams_slots": {
                "0": 954.5,
                "1": 1000.0,
                "2": 1000.0,
                "3": 1000.0,
                "254": 931.56,
            },
            "ams_trays_info": {
                "254": {
                    "id": "254",
                    "empty": False,
                    "type": "TPU",
                    "sub_brands": "",
                    "color": "#BCBCBC",
                    "remain": 0,
                }
            },
        }
        p = BambuPrinter(p_cfg, storage=MagicMock())
        p.active_ams_tray = 254

        # 1. Hardware property must be False
        self.assertFalse(p.has_ams)

        # 2. Status card must NOT contain AMS slots, only VT
        card = build_printer_status_card(p, is_en=False)
        self.assertNotIn("🌈 <b>Слоти AMS:</b>", card)
        self.assertIn("🧵 <b>Філамент (VT):</b>", card)
        self.assertIn("TPU", card)
        self.assertIn("932g", card)

        # 3. Keyboard must contain ONLY VT and Back (no A1..A4!)
        kb = get_ams_slots_keyboard(p, lang="uk")
        self.assertEqual(len(kb.keyboard), 2)  # [VT], [Back]
        btn_texts = [btn.text for row in kb.keyboard for btn in row]
        self.assertTrue(any("VT:" in t for t in btn_texts))
        self.assertFalse(any("A1:" in t for t in btn_texts))
        self.assertFalse(any("A2:" in t for t in btn_texts))
        self.assertFalse(any("A3:" in t for t in btn_texts))
        self.assertFalse(any("A4:" in t for t in btn_texts))


if __name__ == "__main__":
    unittest.main()

