"""
Unit tests for BambuPrinter model.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models.printer import BambuPrinter
from storage.manager import StorageManager


class TestPrinterModel(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.storage = StorageManager(self.temp_path)
        self.config = {
            "id": "test_p1",
            "name": "Test Printer P1S",
            "ip": "192.168.1.100",
            "accessCode": "12345678",
            "serialNumber": "01P00A123456789",
            "filament_grams": 1000.0,
            "price_per_kg": 650.0,
            "power_watts": 120.0,
            "electricity_rate_uah": 4.32,
        }
        self.printer = BambuPrinter(self.config, self.storage)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_calculate_job_cost(self) -> None:
        # 100g weight, default electricity cost calculation (60 mins)
        cost_info = self.printer.calculate_job_cost(100.0, print_mins=60)
        self.assertGreater(cost_info["filament_cost"], 0.0)
        self.assertGreater(cost_info["electricity_cost"], 0.0)
        self.assertEqual(cost_info["total_cost"], round(cost_info["filament_cost"] + cost_info["electricity_cost"], 2))

    def test_maintenance_items_keys(self) -> None:
        m_items = self.printer.maintenance_items
        self.assertEqual(set(m_items.keys()), {"rails", "belts"})
        self.assertNotIn("nozzle", m_items)
        self.assertNotIn("filter", m_items)

    def test_calculate_job_cost_zero_or_negative_weight(self) -> None:
        cost_zero = self.printer.calculate_job_cost(0.0)
        self.assertEqual(cost_zero, {"filament_cost": 0.0, "electricity_cost": 0.0, "total_cost": 0.0})

        cost_neg = self.printer.calculate_job_cost(-15.5)
        self.assertEqual(cost_neg, {"filament_cost": 0.0, "electricity_cost": 0.0, "total_cost": 0.0})

    def test_calculate_job_cost_fallback_minutes(self) -> None:
        # For 100g weight with print_mins=0, effective_mins = max(10, int(100 * 2.0)) = 200 mins
        cost_info = self.printer.calculate_job_cost(100.0, print_mins=0)
        expected_filament = (100.0 / 1000.0) * 650.0  # 65.0
        expected_kwh = (120.0 / 1000.0) * (200.0 / 60.0)  # 0.4 kWh
        expected_elec = round(expected_kwh * 4.32, 2)  # 1.73 UAH
        self.assertEqual(cost_info["filament_cost"], 65.0)
        self.assertEqual(cost_info["electricity_cost"], expected_elec)
        self.assertEqual(cost_info["total_cost"], round(65.0 + expected_elec, 2))

    def test_filament_deduction(self) -> None:
        self.assertEqual(self.printer.filament_grams, 1000.0)
        job_weight = 45.5
        self.printer._current_job_grams = job_weight
        self.printer.gcode_state = "RUNNING"

        # Simulate deduction logic
        self.printer.filament_grams = round(self.printer.filament_grams - self.printer._current_job_grams, 2)
        self.printer._job_deducted = True

        self.assertEqual(self.printer.filament_grams, 954.5)
        self.assertTrue(self.printer._job_deducted)

    def test_negative_filament_deficit(self) -> None:
        self.printer.filament_grams = 3.0
        job_weight = 6.47
        self.printer.filament_grams = round(self.printer.filament_grams - job_weight, 2)
        self.assertEqual(self.printer.filament_grams, -3.47)

    # ==================== _on_message Tests ====================

    def test_on_message_handles_malformed_json(self) -> None:
        msg = MagicMock()
        msg.payload = b"invalid json payload {{{{"
        self.printer._on_message(None, None, msg)
        self.assertTrue(self.printer.is_mqtt_connected)

    def test_on_message_handles_partial_ams_payload(self) -> None:
        msg = MagicMock()
        payload_dict = {
            "print": {
                "gcode_state": "RUNNING",
                "ams": {"ams_exist_bits": "1", "tray_now": "0", "ams": [{"humidity": "4", "temp": "23.5"}]},
            }
        }
        msg.payload = json.dumps(payload_dict).encode("utf-8")
        self.printer._on_message(None, None, msg)

        self.assertEqual(self.printer.gcode_state, "RUNNING")
        self.assertEqual(self.printer.active_ams_tray, 0)
        self.assertEqual(self.printer.ams_humidity_idx, 4)
        self.assertEqual(self.printer.ams_temp, 23.5)

    def test_on_message_handles_invalid_data_types(self) -> None:
        msg = MagicMock()
        payload_dict = {
            "print": {
                "gcode_state": "RUNNING",
                "nozzle_temper": "invalid_number",
                "bed_temper": None,
                "mc_percent": "abc",
                "mc_remaining_time": -50,
                "layer_num": "xyz",
                "spd_lvl": "not_an_int",
            }
        }
        msg.payload = json.dumps(payload_dict).encode("utf-8")
        self.printer._on_message(None, None, msg)

        self.assertEqual(self.printer.nozzle_temper, 0)
        self.assertEqual(self.printer.bed_temper, 0)
        self.assertEqual(self.printer.mc_percent, 0)
        self.assertEqual(self.printer.mc_remaining_time, 0)

    def test_on_message_parses_hms_and_chamber_light(self) -> None:
        msg = MagicMock()
        payload_dict = {
            "print": {
                "gcode_state": "RUNNING",
                "lights_report": [{"node": "chamber_light", "mode": "on"}],
                "hms": [{"code": 134217728, "attr": 65536}],
            }
        }
        msg.payload = json.dumps(payload_dict).encode("utf-8")
        self.printer._on_message(None, None, msg)

        self.assertEqual(self.printer.chamber_light_state, "on")
        self.assertEqual(len(self.printer.hms_errors), 1)
        self.assertEqual(self.printer.hms_errors[0]["code"], 134217728)

    def test_on_message_subtask_weight_regex(self) -> None:
        msg = MagicMock()
        payload_dict = {"print": {"gcode_state": "RUNNING", "subtask_name": "test_model_155.5g.gcode"}}
        msg.payload = json.dumps(payload_dict).encode("utf-8")
        with patch("models.printer.STORAGE_DIR", self.temp_path):
            self.printer._on_message(None, None, msg)

        self.assertEqual(self.printer._current_job_grams, 155.5)

    # ==================== Printer Control Tests ====================

    def test_control_commands_return_false_when_disconnected(self) -> None:
        self.printer._client = None
        self.assertFalse(self.printer.pause())
        self.assertFalse(self.printer.pause_print())
        self.assertFalse(self.printer.resume())
        self.assertFalse(self.printer.resume_print())
        self.assertFalse(self.printer.stop_print())
        self.assertFalse(self.printer.set_speed_level(2))

        # Mock client disconnected
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        self.printer._client = mock_client
        self.assertFalse(self.printer.pause())
        self.assertFalse(self.printer.resume())
        self.assertFalse(self.printer.stop_print())

    def test_control_commands_publish_mqtt_payload_when_connected(self) -> None:
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        self.printer._client = mock_client

        # Test pause
        self.assertTrue(self.printer.pause())
        mock_client.publish.assert_called()
        topic, payload_str = mock_client.publish.call_args[0]
        self.assertEqual(topic, "device/01P00A123456789/request")
        payload = json.loads(payload_str)
        self.assertEqual(payload["print"]["command"], "pause")

        # Test resume
        self.assertTrue(self.printer.resume())
        topic, payload_str = mock_client.publish.call_args[0]
        self.assertEqual(topic, "device/01P00A123456789/request")
        payload = json.loads(payload_str)
        self.assertEqual(payload["print"]["command"], "resume")

        # Test stop_print
        self.assertTrue(self.printer.stop_print())
        topic, payload_str = mock_client.publish.call_args[0]
        self.assertEqual(topic, "device/01P00A123456789/request")
        payload = json.loads(payload_str)
        self.assertEqual(payload["print"]["command"], "stop")

    def test_set_speed_level_clamping_and_mqtt(self) -> None:
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        self.printer._client = mock_client

        # Level 0 -> clamped to 1
        self.assertTrue(self.printer.set_speed_level(0))
        _, payload_str = mock_client.publish.call_args[0]
        payload = json.loads(payload_str)
        self.assertEqual(payload["print"]["param"], "1")

        # Level 5 -> clamped to 4
        self.assertTrue(self.printer.set_speed_level(5))
        _, payload_str = mock_client.publish.call_args[0]
        payload = json.loads(payload_str)
        self.assertEqual(payload["print"]["param"], "4")

    @patch("asyncio.run_coroutine_threadsafe")
    def test_history_recording_on_finish(self, mock_threadsafe) -> None:
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        self.printer._main_loop = mock_loop
        self.printer.subtask_name = "Benchy_35g.3mf"
        self.printer.filament_type = "PLA"

        msg = MagicMock()
        msg.topic = f"device/{self.printer.serial_number}/report"
        msg.payload = json.dumps({"print": {"gcode_state": "RUNNING", "mc_percent": 50}}).encode("utf-8")
        self.printer._on_message(None, None, msg)
        self.assertTrue(self.printer._is_printing)
        self.assertFalse(self.printer._history_recorded)

        # Transition to FINISH
        msg.payload = json.dumps({"print": {"gcode_state": "FINISH", "mc_percent": 100}}).encode("utf-8")
        self.printer._on_message(None, None, msg)
        self.assertTrue(self.printer._history_recorded)
        self.assertFalse(self.printer._is_printing)
        mock_threadsafe.assert_called_once()
        coro = mock_threadsafe.call_args[0][0]
        coro.close()

    @patch("asyncio.run_coroutine_threadsafe")
    def test_no_phantom_history_on_initial_finish(self, mock_threadsafe) -> None:
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        self.printer._main_loop = mock_loop
        self.printer._is_printing = False
        self.printer.subtask_name = "OldModel.3mf"

        msg = MagicMock()
        msg.topic = f"device/{self.printer.serial_number}/report"
        msg.payload = json.dumps({"print": {"gcode_state": "FINISH", "mc_percent": 100}}).encode("utf-8")
        self.printer._on_message(None, None, msg)

        mock_threadsafe.assert_not_called()

    @patch("asyncio.run_coroutine_threadsafe")
    def test_history_recording_when_started_from_app(self, mock_threadsafe) -> None:
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        self.printer._main_loop = mock_loop
        self.printer.subtask_name = "AppModel_20g.3mf"
        self.printer._job_started_from_app = True
        self.printer._was_running = True

        msg = MagicMock()
        msg.topic = f"device/{self.printer.serial_number}/report"
        msg.payload = json.dumps({"print": {"gcode_state": "IDLE", "mc_percent": 0}}).encode("utf-8")
        self.printer._on_message(None, None, msg)

        msg.payload = json.dumps({"print": {"gcode_state": "FINISH", "mc_percent": 100}}).encode("utf-8")
        self.printer._on_message(None, None, msg)
        self.assertTrue(self.printer._history_recorded)
        mock_threadsafe.assert_called_once()
        coro = mock_threadsafe.call_args[0][0]
        coro.close()

    def test_subtask_weight_reset_for_identical_filename(self) -> None:
        self.printer._current_job_grams = 150.0
        self.printer._last_subtask_name = "box.3mf"

        msg = MagicMock()
        msg.topic = f"device/{self.printer.serial_number}/report"
        msg.payload = json.dumps({"print": {"gcode_state": "RUNNING", "subtask_name": "box_45g.3mf", "mc_percent": 10}}).encode("utf-8")
        self.printer._on_message(None, None, msg)

        self.assertEqual(self.printer._current_job_grams, 45.0)


if __name__ == "__main__":
    unittest.main()
