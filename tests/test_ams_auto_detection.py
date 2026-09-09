import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from models.printer import BambuPrinter, build_ams_mapping
from services.gcode_parser import check_compatibility, normalize_filament_name
from services.mqtt_message_parser import parse_mqtt_payload


class TestAMSAutoDetectionAndMapping(unittest.TestCase):
    def setUp(self):
        self.printer_cfg = {
            "id": "test_p1s",
            "name": "Bambu Lab P1S",
            "ip": "192.168.1.100",
            "accessCode": "12345678",
            "serialNumber": "01P00A123456789",
            "printer_model": "P1S",
        }
        self.printer = BambuPrinter(self.printer_cfg, storage=MagicMock())
        self.printer._client = MagicMock()
        self.printer._client.is_connected.return_value = True

    def test_mqtt_parser_with_ams_items_bambu_format(self):
        """Tests parsing telemetry with ams_items containing filled and empty slots."""
        payload = {
            "print": {
                "gcode_state": "IDLE",
                "ams": {
                    "ams_exist_bits": "1",
                    "ams_items": [
                        {
                            "id": "0",
                            "tray": [
                                {"id": "0", "remain": 72, "tray_color": "FF0000FF", "tray_type": "PLA"},
                                {"id": "1", "remain": -1, "tray_color": "00000000", "tray_type": "empty"},
                                {"id": "2", "remain": 15, "tray_color": "FFFFFFFF", "tray_type": "ABS"},
                                {"id": "3", "remain": 94, "tray_color": "0000FFFF", "tray_type": "PETG"},
                            ],
                        }
                    ],
                },
            }
        }
        parsed = parse_mqtt_payload(json.dumps(payload))
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed.get("has_ams"))
        self.assertEqual(parsed.get("ams_exist_bits"), "1")
        trays = parsed.get("ams_trays_info", {})
        self.assertEqual(len(trays), 4)

        # Slot 0: PLA
        self.assertEqual(trays["0"]["type"], "PLA")
        self.assertEqual(trays["0"]["color"], "#FF0000")
        self.assertFalse(trays["0"]["empty"])
        self.assertEqual(trays["0"]["remain"], 72)

        # Slot 1: empty
        self.assertTrue(trays["1"]["empty"])
        self.assertEqual(trays["1"]["type"], "")

        # Slot 2: ABS
        self.assertEqual(trays["2"]["type"], "ABS")
        self.assertFalse(trays["2"]["empty"])

        # Slot 3: PETG
        self.assertEqual(trays["3"]["type"], "PETG")
        self.assertFalse(trays["3"]["empty"])

    def test_mqtt_parser_no_ams(self):
        """Tests parsing telemetry without AMS or with empty ams_items."""
        # 1. Empty ams_items
        payload_empty = {
            "print": {
                "ams": {
                    "ams_exist_bits": "0",
                    "ams_items": [],
                }
            }
        }
        parsed = parse_mqtt_payload(json.dumps(payload_empty))
        self.assertFalse(parsed.get("has_ams"))

        # 2. No ams key at all
        payload_no_ams = {"print": {"gcode_state": "RUNNING"}}
        parsed2 = parse_mqtt_payload(json.dumps(payload_no_ams))
        self.assertIsNone(parsed2.get("has_ams"))

    def test_printer_state_manager_update(self):
        """Tests BambuPrinter updating has_ams and ams_trays_info from MQTT message."""
        msg = MagicMock()
        msg.topic = f"device/{self.printer.serial_number}/report"
        payload = {
            "print": {
                "ams": {
                    "ams_exist_bits": "1",
                    "ams_items": [
                        {
                            "id": "0",
                            "tray": [
                                {"id": "0", "remain": -1, "tray_type": "empty"},
                                {"id": "1", "remain": 50, "tray_type": "ABS", "tray_color": "161616FF"},
                                {"id": "2", "remain": 80, "tray_type": "PETG", "tray_color": "161616FF"},
                                {"id": "3", "remain": -1, "tray_type": ""},
                            ],
                        }
                    ],
                }
            }
        }
        msg.payload = json.dumps(payload).encode("utf-8")
        self.printer._on_message(self.printer._client, None, msg)

        self.assertTrue(self.printer.has_ams)
        self.assertEqual(self.printer.find_matching_ams_slot("ABS"), 1)   # Slot 2 (index 1)
        self.assertEqual(self.printer.find_matching_ams_slot("PETG"), 2)  # Slot 3 (index 2)
        self.assertIsNone(self.printer.find_matching_ams_slot("PLA"))     # Not loaded
        self.assertIsNone(self.printer.find_matching_ams_slot("TPU"))     # Not loaded

        summary = self.printer.get_loaded_ams_summary()
        self.assertIn("Слот 1: порожній", summary)
        self.assertIn("Слот 2: ABS", summary)
        self.assertIn("Слот 3: PETG", summary)
        self.assertIn("Слот 4: порожній", summary)

    def test_check_compatibility_with_ams_printer(self):
        """Tests check_compatibility recognizing materials loaded in any AMS slot."""
        # Set AMS state on printer: Slot 2 (ABS), Slot 3 (PETG)
        self.printer._has_ams_telemetry = True
        self.printer.ams_trays_info = {
            "0": {"id": "0", "type": "", "empty": True},
            "1": {"id": "1", "type": "ABS", "empty": False},
            "2": {"id": "2", "type": "PETG", "empty": False},
            "3": {"id": "3", "type": "", "empty": True},
        }

        # Compatible with ABS (found in Slot 2)
        res_abs = check_compatibility("P1S", "ABS", self.printer.name, printer=self.printer)
        self.assertTrue(res_abs["compatible"])
        self.assertEqual(res_abs.get("matched_ams_slot"), 2)

        # Compatible with PETG (found in Slot 3)
        res_petg = check_compatibility("P1S", "PETG", self.printer.name, printer=self.printer)
        self.assertTrue(res_petg["compatible"])
        self.assertEqual(res_petg.get("matched_ams_slot"), 3)

        # Incompatible with PLA (PLA is not loaded in AMS)
        res_pla = check_compatibility("P1S", "PLA", self.printer.name, printer=self.printer)
        self.assertFalse(res_pla["compatible"])
        self.assertEqual(res_pla.get("reason_type"), "FILAMENT")

    def test_start_print_job_async_auto_slot_selection(self):
        """Tests start_print_job_async automatically detecting matching slot and generating ams_mapping."""
        import asyncio

        # Setup printer with AMS containing PETG in Slot 3 (index 2) and PLA in Slot 4 (index 3)
        self.printer._has_ams_telemetry = True
        self.printer.ams_trays_info = {
            "0": {"id": "0", "type": "", "empty": True},
            "1": {"id": "1", "type": "", "empty": True},
            "2": {"id": "2", "type": "PETG", "empty": False},
            "3": {"id": "3", "type": "PLA", "empty": False},
        }

        with patch("models.printer.upload_3mf_to_bambu", return_value="file:///sdcard/auto_pla.3mf"), \
             patch("models.printer.verify_bambu_file_size", return_value=True), \
             patch("models.printer.parse_3mf_file", return_value={"filament_type": "PLA", "weight_g": 35.0, "objects": []}):
            # Auto-select slot for 3MF with PLA
            loop = asyncio.new_event_loop()
            ok, msg = loop.run_until_complete(
                self.printer.start_print_job_async(b"dummy 3mf content", "auto_pla.3mf")
            )
            loop.close()

            self.assertTrue(ok)
            self.printer._client.publish.assert_called()
            call_args = self.printer._client.publish.call_args[0]
            payload_str = call_args[1]
            payload = json.loads(payload_str)

            # PLA was in slot index 3 (Slot 4) -> ams_mapping must be [3, -1, -1, -1]!
            self.assertTrue(payload["print"]["use_ams"])
            self.assertEqual(payload["print"]["ams_mapping"], [3, -1, -1, -1])

    def test_start_print_job_async_missing_filament_blocks_start(self):
        """Tests start_print_job_async returning an informative error when required filament is not in AMS."""
        import asyncio

        # Setup printer with AMS containing ONLY ABS in Slot 2
        self.printer._has_ams_telemetry = True
        self.printer.ams_trays_info = {
            "0": {"id": "0", "type": "", "empty": True},
            "1": {"id": "1", "type": "ABS", "empty": False},
            "2": {"id": "2", "type": "", "empty": True},
            "3": {"id": "3", "type": "", "empty": True},
        }

        with patch("models.printer.upload_3mf_to_bambu", return_value="file:///sdcard/petg_part.3mf"), \
             patch("models.printer.verify_bambu_file_size", return_value=True), \
             patch("models.printer.parse_3mf_file", return_value={"filament_type": "PETG", "weight_g": 20.0, "objects": []}):
            loop = asyncio.new_event_loop()
            ok, msg = loop.run_until_complete(
                self.printer.start_print_job_async(b"dummy 3mf content", "petg_part.3mf")
            )
            loop.close()

            # Must return False and inform user
            self.assertFalse(ok)
            self.assertIn("Невідповідність філаменту в AMS", msg)
            self.assertIn("PETG", msg)
            self.assertIn("Слот 2: ABS", msg)

    def test_start_print_job_async_without_ams(self):
        """Tests start_print_job_async when printer has no AMS (use_ams=False, ams_mapping=[])."""
        import asyncio

        self.printer._has_ams_telemetry = False
        self.printer.ams_trays_info = {}

        with patch("models.printer.upload_3mf_to_bambu", return_value="file:///sdcard/no_ams.3mf"), \
             patch("models.printer.verify_bambu_file_size", return_value=True), \
             patch("models.printer.parse_3mf_file", return_value={"filament_type": "PLA", "weight_g": 10.0, "objects": []}):
            loop = asyncio.new_event_loop()
            ok, msg = loop.run_until_complete(
                self.printer.start_print_job_async(b"dummy 3mf content", "no_ams.3mf")
            )
            loop.close()

            self.assertTrue(ok)
            self.printer._client.publish.assert_called()
            payload = json.loads(self.printer._client.publish.call_args[0][1])

            self.assertFalse(payload["print"]["use_ams"])
            self.assertEqual(payload["print"]["ams_mapping"], [])


if __name__ == "__main__":
    unittest.main()
