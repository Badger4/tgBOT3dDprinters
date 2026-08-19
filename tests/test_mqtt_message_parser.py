"""
Unit tests for services.mqtt_message_parser module.
"""

import json
import unittest

from services.mqtt_message_parser import extract_subtask_weight, parse_mqtt_payload


class TestMQTTMessageParser(unittest.TestCase):
    def test_parse_mqtt_payload_valid_dict(self) -> None:
        payload = json.dumps(
            {
                "print": {
                    "gcode_state": "running",
                    "nozzle_temper": "215.4",
                    "bed_temper": "60.0",
                    "mc_percent": "45",
                    "mc_remaining_time": "120",
                    "layer_num": "12",
                    "total_layer_num": "100",
                    "subtask_name": "gear_150g.gcode",
                    "spd_lvl": "2",
                    "spd_mag": "100",
                    "nozzle_target_temper": "220.0",
                    "bed_target_temper": "60.0",
                    "chamber_temper": "35.0",
                    "wifi_signal": "-48dBm",
                    "xcam": {
                        "spaghetti_detector": True,
                        "first_layer_inspector": True,
                        "printing_monitor": True,
                        "print_halt": True
                    },
                    "upgrade_state": {
                        "new_version_state": 1,
                        "ota_new_version_number": "01.08.00.00",
                        "force_upgrade": False
                    },
                    "upload": {
                        "status": "running",
                        "progress": 85
                    },
                    "lights_report": [{"node": "chamber_light", "mode": "on"}],
                    "hms": [{"code": 1001, "attr": 1}],
                    "ams": {
                        "ams_exist_bits": "1",
                        "tray_now": "1",
                        "ams": [
                            {
                                "humidity": "3",
                                "temp": "24.5",
                                "tray": [
                                    {
                                        "id": "1",
                                        "empty": False,
                                        "tray_color": "FF0000FF",
                                        "tray_type": "PLA",
                                        "remain": 80,
                                        "tag_uid": "ABC123XYZ",
                                    }
                                ],
                            }
                        ],
                    },
                }
            }
        ).encode("utf-8")

        parsed = parse_mqtt_payload(payload)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["gcode_state"], "RUNNING")
        self.assertEqual(parsed["nozzle_temper"], 215)
        self.assertEqual(parsed["nozzle_target_temper"], 220)
        self.assertEqual(parsed["bed_temper"], 60)
        self.assertEqual(parsed["bed_target_temper"], 60)
        self.assertEqual(parsed["chamber_temper"], 35)
        self.assertEqual(parsed["wifi_signal"], "-48dBm")
        self.assertTrue(parsed["xcam_info"]["spaghetti_detector"])
        self.assertEqual(parsed["upgrade_state"]["ota_new_version_number"], "01.08.00.00")
        self.assertEqual(parsed["upload_info"]["progress"], 85)
        self.assertEqual(parsed["mc_percent"], 45)
        self.assertEqual(parsed["mc_remaining_time"], 120)
        self.assertEqual(parsed["layer_num"], 12)
        self.assertEqual(parsed["total_layer_num"], 100)
        self.assertEqual(parsed["subtask_name"], "gear_150g.gcode")
        self.assertEqual(parsed["chamber_light_state"], "on")
        self.assertEqual(parsed["hms_errors"], [{"code": 1001, "attr": 1}])
        self.assertEqual(parsed["ams_trays_info"]["1"]["color"], "#FF0000")
        self.assertEqual(parsed["ams_trays_info"]["1"]["type"], "PLA")
        self.assertEqual(parsed["ams_trays_info"]["1"]["tag_uid"], "ABC123XYZ")

    def test_parse_mqtt_payload_invalid_inputs(self) -> None:
        self.assertIsNone(parse_mqtt_payload(b"invalid json"))
        self.assertIsNone(parse_mqtt_payload("invalid json"))
        self.assertIsNone(parse_mqtt_payload(12345))  # type: ignore
        self.assertIsNone(parse_mqtt_payload(json.dumps({"no_print": 1})))

    def test_extract_subtask_weight(self) -> None:
        self.assertEqual(extract_subtask_weight("gear_box_125.5g.gcode"), 125.5)
        self.assertEqual(extract_subtask_weight("housing_45g.3mf"), 45.0)
        self.assertEqual(extract_subtask_weight("no_weight_filename.gcode"), 0.0)
        self.assertEqual(extract_subtask_weight(""), 0.0)


if __name__ == "__main__":
    unittest.main()
