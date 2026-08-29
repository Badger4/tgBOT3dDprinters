"""
Unit tests for spool fingerprinting, active print context persistence, AMS delta detection, and humidity raw parsing.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import config
from models.printer import BambuPrinter
from services.mqtt_message_parser import parse_mqtt_payload
from utils.spool_fingerprint import (
    build_spool_fingerprint,
    delete_active_print_context,
    load_active_print_context,
    save_active_print_context,
)


class TestSpoolFingerprintAndContext(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.orig_storage_dir = config.STORAGE_DIR
        config.STORAGE_DIR = self.test_dir

        self.printer = BambuPrinter(
            {
                "id": "test_p1",
                "name": "Test Printer 1",
                "ip": "127.0.0.1",
                "access_code": "12345678",
                "serial_number": "01P00A123456",
                "ams_slots": {"0": 1000.0, "1": 500.0, "2": 0.0, "3": 750.0, "255": 1000.0},
            },
            storage=MagicMock(),
        )

    def tearDown(self):
        config.STORAGE_DIR = self.orig_storage_dir
        self.temp_dir.cleanup()

    def test_build_spool_fingerprint(self):
        fp = build_spool_fingerprint(self.printer)
        self.assertIn("0=", fp)
        self.assertIn("1000.0", fp)
        self.assertIn("500.0", fp)

    def test_save_load_delete_context(self):
        ctx = {
            "printer_id": self.printer.id,
            "subtask_name": "Cube_20g.3mf",
            "saved_layer": 5,
            "spool_fingerprint": build_spool_fingerprint(self.printer),
            "job_grams": 20.0,
            "job_deducted": True,
        }

        save_active_print_context(self.printer.id, ctx)
        loaded = load_active_print_context(self.printer.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["subtask_name"], "Cube_20g.3mf")
        self.assertEqual(loaded["job_grams"], 20.0)

        delete_active_print_context(self.printer.id)
        self.assertIsNone(load_active_print_context(self.printer.id))

    def test_humidity_raw_parsing(self):
        raw_msg = {
            "print": {
                "ams": {
                    "ams": [
                        {
                            "id": "0",
                            "humidity": "4",
                            "humidity_raw": "42",
                            "temp": "25.5",
                        }
                    ]
                }
            }
        }
        parsed = parse_mqtt_payload(raw_msg)
        self.assertEqual(parsed.get("ams_humidity_idx"), 4)
        self.assertEqual(parsed.get("ams_humidity_raw"), 42)

    def test_ams_slot_delta_detection(self):
        self.printer._previous_ams_slots = {"0": 1000.0, "1": 0.0, "2": 500.0}
        self.printer.ams_slots = {"0": 1000.0, "1": 800.0, "2": 0.0}

        with self.assertLogs(level="INFO") as cm:
            old_slots = dict(self.printer._previous_ams_slots)
            for slot_key, new_weight in self.printer.ams_slots.items():
                old_weight = old_slots.get(slot_key, 0.0)
                if old_weight == 0.0 and new_weight > 0.0:
                    config.logger.info(f"[AMS] Нова котушка вставлена в слот {slot_key} на {self.printer.name}")
                elif old_weight > 0.0 and new_weight == 0.0:
                    config.logger.info(f"[AMS] Котушку витягнуто зі слоту {slot_key} на {self.printer.name}")

            output = "\n".join(cm.output)
            self.assertIn("Нова котушка вставлена в слот 1", output)
            self.assertIn("Котушку витягнуто зі слоту 2", output)


if __name__ == "__main__":
    unittest.main()
