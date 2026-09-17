import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from models.printer import BambuPrinter
from app import PrinterBotApp
import services.http.routes_control as routes_control
from aiohttp import web


class TestFilamentHardwareSync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.printer_cfg = {
            "id": "p1",
            "name": "Bambu Lab P1S",
            "ip": "192.168.1.101",
            "accessCode": "12345678",
            "serialNumber": "01P00A123456789",
            "printer_model": "P1S",
        }
        self.printer = BambuPrinter(self.printer_cfg, storage=MagicMock())
        self.printer._client = MagicMock()
        self.printer._client.is_connected.return_value = True
        self.printer._client.publish = MagicMock()

    def test_unload_filament_safety(self):
        # 1. When is_printing is True, unload should be blocked
        self.printer.is_printing = True
        self.printer.gcode_state = "IDLE"
        self.assertFalse(self.printer.unload_filament(0))
        self.printer._client.publish.assert_not_called()

        # 2. When gcode_state is RUNNING, unload should be blocked
        self.printer.is_printing = False
        self.printer.gcode_state = "RUNNING"
        self.assertFalse(self.printer.unload_filament(0))

        # 3. When gcode_state is PAUSE, unload should be blocked
        self.printer.gcode_state = "PAUSE"
        self.assertFalse(self.printer.unload_filament(0))

    def test_unload_filament_success(self):
        self.printer.is_printing = False
        self.printer.gcode_state = "IDLE"
        
        result = self.printer.unload_filament("0")
        self.assertTrue(result)
        # Should publish unload commands
        self.assertGreaterEqual(self.printer._client.publish.call_count, 1)

    def test_load_filament_safety(self):
        self.printer.is_printing = True
        self.printer.gcode_state = "IDLE"
        self.assertFalse(self.printer.load_filament(0))
        self.printer._client.publish.assert_not_called()

        self.printer.is_printing = False
        self.printer.gcode_state = "PREPARE"
        self.assertFalse(self.printer.load_filament(0))

    def test_load_filament_success(self):
        self.printer.is_printing = False
        self.printer.gcode_state = "IDLE"
        
        result = self.printer.load_filament("0", target_temp=220)
        self.assertTrue(result)
        self.assertGreaterEqual(self.printer._client.publish.call_count, 1)

    def test_tray_state_deltas_initialization_and_events(self):
        events = []
        self.printer.tray_event_callback = lambda p, evt: events.append(evt)

        # 1. Baseline state
        self.printer.ams_trays_info = {
            "0": {"type": "PLA", "tray_type": "PLA", "color": "#FF0000", "tray_color": "FF0000FF", "empty": False},
            "1": {"type": "", "tray_type": "empty", "color": "", "tray_color": "00000000", "empty": True},
        }
        self.printer._check_tray_state_deltas()
        self.assertTrue(self.printer._trays_initialized)
        self.assertEqual(len(events), 0)

        # 2. Tray 0 unloaded on printer
        self.printer.ams_trays_info["0"] = {"type": "", "tray_type": "empty", "color": "", "tray_color": "00000000", "empty": True}
        self.printer._check_tray_state_deltas()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "tray_unloaded")
        self.assertEqual(events[0]["slot_id"], "0")
        self.assertEqual(events[0]["printer_id"], "p1")

        # 3. Tray 1 loaded on printer
        self.printer.ams_trays_info["1"] = {"type": "PETG", "tray_type": "PETG", "color": "#00FF00", "tray_color": "00FF00FF", "empty": False}
        self.printer._check_tray_state_deltas()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["event"], "tray_loaded")
        self.assertEqual(events[1]["slot_id"], "1")
        self.assertEqual(events[1]["filament_type"], "PETG")

    async def test_handle_tray_event_unloaded(self):
        bot_app = PrinterBotApp()
        bot_app.storage = MagicMock()
        bot_app.save_printers_config = AsyncMock()
        bot_app.send_notification = AsyncMock()

        spool = {
            "id": "spool_123",
            "name": "Red PLA",
            "type": "PLA",
            "color": "#FF0000",
            "remaining_grams": 750,
            "assigned_printer_id": "p1",
            "assigned_slot_key": "0",
        }
        bot_app.storage.load_spools = AsyncMock(return_value={"spool_123": spool})
        bot_app.storage.save_spools = AsyncMock()
        bot_app.storage.record_spool_movement = AsyncMock()

        event = {
            "event": "tray_unloaded",
            "slot_id": "0",
            "printer_id": "p1",
            "printer_name": "Bambu Lab P1S",
            "prev_type": "PLA",
            "timestamp": 1234567890.0,
        }

        with patch("bot.handlers.filament.add.unassign_spool_from_slot", return_value=("повернено", 1)):
            await bot_app.handle_tray_event(self.printer, event)

        bot_app.storage.save_spools.assert_called_once()
        bot_app.storage.record_spool_movement.assert_called_once()
        bot_app.send_notification.assert_called_once()
        args, kwargs = bot_app.send_notification.call_args
        self.assertEqual(args[0], "finish")
        self.assertIn("автоматично знято зі слоту", args[1])

    async def test_handle_tray_event_loaded(self):
        bot_app = PrinterBotApp()
        bot_app.send_notification = AsyncMock()

        event = {
            "event": "tray_loaded",
            "slot_id": "0",
            "printer_id": "p1",
            "printer_name": "Bambu Lab P1S",
            "filament_type": "PLA",
            "color": "#FF0000",
        }

        await bot_app.handle_tray_event(self.printer, event)

        bot_app.send_notification.assert_called_once()
        args, kwargs = bot_app.send_notification.call_args
        self.assertEqual(args[0], "start")
        self.assertIn("завантажено новий філамент", args[1])
        self.assertIn("reply_markup", kwargs)
        markup = kwargs["reply_markup"]
        self.assertIsNotNone(markup)

    async def test_routes_control_unload_and_load(self):
        app_mock = MagicMock()
        printer_mock = MagicMock()
        printer_mock.is_printing = False
        printer_mock.gcode_state = "IDLE"
        printer_mock.unload_filament = MagicMock(return_value=True)
        printer_mock.load_filament = MagicMock(return_value=True)
        app_mock.printers = {"p1": printer_mock}
        app_mock.spool_storage = MagicMock()

        with patch("services.http.routes_control.check_auth", return_value=True):
            # Test standalone unload_filament
            req = AsyncMock()
            req.app = {"app_obj": app_mock}
            req.match_info = {"id": "p1"}
            req.json = AsyncMock(return_value={"action": "unload_filament", "slot_id": "0"})
            resp = await routes_control.handle_printer_control(req)
            self.assertEqual(resp.status, 200)
            printer_mock.unload_filament.assert_called_once_with(slot_id="0")

            # Test standalone load_filament
            req = AsyncMock()
            req.app = {"app_obj": app_mock}
            req.match_info = {"id": "p1"}
            req.json = AsyncMock(return_value={"action": "load_filament", "slot_id": "0", "target_temp": 215})
            resp = await routes_control.handle_printer_control(req)
            self.assertEqual(resp.status, 200)
            printer_mock.load_filament.assert_called_once_with(slot_id="0", target_temp=215)

    async def test_bot_hw_callbacks(self):
        from bot.handlers.filament.mount import (
            handle_hw_unload_callback,
            handle_hw_load_callback,
            handle_hw_skip_callback,
            handle_fil_auto_mount_callback,
            handle_fil_pick_callback,
            handle_fil_auto_add_callback,
            handle_fil_auto_skip_callback,
        )

        app_mock = MagicMock()
        printer_mock = MagicMock()
        printer_mock.name = "P1S"
        printer_mock.id = "p1"
        printer_mock.is_printing = False
        printer_mock.gcode_state = "IDLE"
        printer_mock.unload_filament = MagicMock(return_value=True)
        printer_mock.load_filament = MagicMock(return_value=True)
        app_mock.printers = {"p1": printer_mock}
        app_mock.storage = MagicMock()
        app_mock.storage.load_user = AsyncMock(return_value={"language": "uk"})
        app_mock.storage.save_user = AsyncMock()
        app_mock.storage.load_spools = AsyncMock(return_value={
            "spool_1": {"id": "spool_1", "name": "Bambu PLA", "type": "PLA", "remaining_grams": 1000, "quantity": 1}
        })
        app_mock.storage.save_spools = AsyncMock()
        app_mock.save_printers_config = AsyncMock()

        # 1. hw_unload
        call = AsyncMock()
        call.message.chat.id = 12345
        call.data = "hw_unload:p1:0"
        await handle_hw_unload_callback(call, app_mock)
        printer_mock.unload_filament.assert_called_once_with(slot_id="0")
        call.message.edit_text.assert_called_once()

        # 2. hw_load
        call = AsyncMock()
        call.message.chat.id = 12345
        call.data = "hw_load:p1:0"
        await handle_hw_load_callback(call, app_mock)
        printer_mock.load_filament.assert_called_once_with(slot_id="0")
        call.message.edit_text.assert_called_once()

        # 3. hw_skip
        call = AsyncMock()
        call.data = "hw_skip"
        await handle_hw_skip_callback(call)
        call.message.delete_reply_markup.assert_called_once()

        # 4. fil_auto_mount (shows warehouse list)
        call = AsyncMock()
        call.data = "fil_auto_mount:p1:0:PLA"
        await handle_fil_auto_mount_callback(call, app_mock)
        call.message.edit_text.assert_called_once()

        # 5. fil_pick (selects spool)
        call = AsyncMock()
        call.data = "fil_pick:p1:0:spool_1"
        with patch("bot.handlers.filament.add.assign_spool_to_slot", return_value=({"name": "Bambu PLA"}, 0)):
            await handle_fil_pick_callback(call, app_mock)
        app_mock.storage.save_spools.assert_called_once()
        call.message.edit_text.assert_called_once()

        # 6. fil_auto_add (starts wizard)
        call = AsyncMock()
        call.message.chat.id = 12345
        call.data = "fil_auto_add:p1:0:PETG"
        await handle_fil_auto_add_callback(call, app_mock)
        app_mock.storage.save_user.assert_called_once()
        user_saved = app_mock.storage.save_user.call_args[0][0]
        self.assertEqual(user_saved["state"], "add_spool_name")
        self.assertEqual(user_saved["context_data"]["prefill_type"], "PETG")
        self.assertTrue(user_saved["context_data"]["auto_mount_on_create"])

        # 7. fil_auto_skip
        call = AsyncMock()
        call.data = "fil_auto_skip:p1:0"
        await handle_fil_auto_skip_callback(call)
        call.message.edit_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
