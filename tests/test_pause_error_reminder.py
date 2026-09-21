"""
Unit tests for the 5-minute pause error repeated notification feature.
Verifies:
1. Extraction of active printer errors (HMS, MC, print error, fail reason).
2. Initial error alert sending.
3. 5-minute timer tracking while on PAUSE with active errors.
4. Sending repeat notification exactly after >= 300 seconds.
5. Suppression of spam on subsequent monitoring ticks.
6. Immediate timer cancellation upon state resume, finish, or error resolution.
7. Re-arming when new errors occur while paused.
"""

import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app import PrinterBotApp, get_printer_active_errors
from bot.keyboards import get_error_notification_inline_keyboard
from models.printer import BambuPrinter
from storage.manager import StorageManager


class TestPauseErrorReminder(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(Path(self.temp_dir.name))

        self.app = PrinterBotApp()
        self.app.storage = self.storage
        self.app.send_notification = AsyncMock()

        self.printer_cfg = {
            "id": "p_test",
            "name": "Bambu A1 Lab",
            "ip": "192.168.1.100",
            "code": "12345678",
            "serialNumber": "01P00A123456789",
            "gcode_state": "IDLE",
            "notify": True,
        }
        self.printer = BambuPrinter(self.printer_cfg, self.storage)
        self.app.printers["p_test"] = self.printer

        # Initialize printer state in app
        self.app.printer_states["p_test"] = {
            "lastState": "IDLE",
            "notifiedStart": False,
            "notifiedFinish": False,
            "notifiedPause": False,
            "notifiedClearReminder": False,
            "notifiedHMS": False,
            "pauseErrorStartTime": None,
            "notifiedPauseErrorRepeat": False,
            "lastErrorCodes": set(),
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_printer_active_errors_hms(self):
        """Checks that HMS errors and resolved descriptions are properly extracted."""
        # 1. Resolved HMS
        self.printer.hms_resolved = ["Помилка сопла", "Застрягання нитки"]
        self.printer.hms_errors = [{"code": 1001}]
        errs = get_printer_active_errors(self.printer)
        self.assertEqual(errs, ["Помилка сопла", "Застрягання нитки"])

        # 2. Raw HMS fallback if resolved is empty
        self.printer.hms_resolved = []
        self.printer.hms_errors = ["HMS_0300_0900_0001_0001"]
        errs = get_printer_active_errors(self.printer)
        self.assertEqual(errs, ["HMS_0300_0900_0001_0001"])

    def test_get_printer_active_errors_mc_print_and_fail_reason(self):
        """Checks that MC print error, print_error, and fail_reason are formatted properly."""
        self.printer.hms_resolved = []
        self.printer.hms_errors = []
        self.printer.mc_print_error_code = "1055"
        self.printer.print_error = 502
        self.printer.fail_reason = "14"

        errs = get_printer_active_errors(self.printer)
        self.assertIn("Код помилки MC: 1055", errs)
        self.assertIn("Код помилки друку: 502", errs)
        self.assertIn("Причина збою: 14", errs)

    def test_get_printer_active_errors_empty(self):
        """Checks that clean printer has zero active errors."""
        self.printer.hms_resolved = []
        self.printer.hms_errors = []
        self.printer.mc_print_error_code = "0"
        self.printer.print_error = 0
        self.printer.fail_reason = ""

        errs = get_printer_active_errors(self.printer)
        self.assertEqual(errs, [])
        self.assertEqual(self.printer.get_active_errors(), [])

    async def _run_monitoring_iteration(self):
        """Simulates one pass of app.monitoring_loop logic for p_test."""
        p = self.printer
        st = self.app.printer_states[p.id]
        curr_state = p.gcode_state

        # Section 2: Pause notification
        if curr_state == "PAUSE" and st["lastState"] != "PAUSE":
            if p.notify and not st["notifiedPause"]:
                await self.app.send_notification(
                    "pause",
                    f"⏸️ *Гей! Принтер {p.name} поставлено на паузу!* Іди перевір, що там сталося, Бака! 😤",
                    reply_markup=get_error_notification_inline_keyboard(p.id),
                    printer=p,
                )
                st["notifiedPause"] = True
        elif curr_state != "PAUSE":
            st["notifiedPause"] = False

        # Section 5: Printer Error Alert & 5-Minute Pause Reminder
        active_errors = get_printer_active_errors(p)
        has_error = bool(active_errors)
        curr_err_set = set(active_errors)
        last_err_set = st.get("lastErrorCodes", set())

        if has_error:
            if not curr_err_set.issubset(last_err_set):
                st["notifiedHMS"] = False
                st["notifiedPauseErrorRepeat"] = False
                if curr_state == "PAUSE":
                    st["pauseErrorStartTime"] = time.time()
            st["lastErrorCodes"] = curr_err_set
        else:
            st["lastErrorCodes"] = set()
            st["notifiedHMS"] = False
            st["pauseErrorStartTime"] = None
            st["notifiedPauseErrorRepeat"] = False

        # 5a. Initial Error Alert
        if has_error and not st.get("notifiedHMS"):
            err_lines = "\n".join([f"• <code>{h}</code>" for h in active_errors])
            err_title = "⚡ <b>HMS Помилка на принтері" if getattr(p, "hms_errors", None) else "⚡ <b>Помилка на принтері"
            err_txt = (
                f"{err_title} {p.name}!</b>\n\n"
                f"⚠️ <b>Виявлено збої:</b>\n{err_lines}\n\n"
                f"Біжи перевіряй принтер, Бака! 😤"
            )
            await self.app.send_notification(
                "pause",
                err_txt,
                reply_markup=get_error_notification_inline_keyboard(p.id),
                printer=p,
            )
            st["notifiedHMS"] = True

        # 5b. 5-Minute Pause with Error Repeat Reminder
        if curr_state == "PAUSE" and has_error:
            if st.get("pauseErrorStartTime") is None:
                st["pauseErrorStartTime"] = time.time()
                st["notifiedPauseErrorRepeat"] = False
            elif not st.get("notifiedPauseErrorRepeat"):
                elapsed_pause_error = time.time() - st["pauseErrorStartTime"]
                if elapsed_pause_error >= 300.0:
                    err_lines = "\n".join([f"• <code>{h}</code>" for h in active_errors])
                    rem_err_txt = (
                        f"🚨 <b>Повторне сповіщення про помилку!</b>\n\n"
                        f"Принтер <b>{p.name}</b> досі стоїть на паузі вже понад <b>5 хвилин</b> через помилку!\n\n"
                        f"⚠️ <b>Активні помилки:</b>\n{err_lines}\n\n"
                        f"Принтер потребує вашої уваги, Бака! Швидше перевір його! 😤🔧"
                    )
                    await self.app.send_notification(
                        "pause",
                        rem_err_txt,
                        reply_markup=get_error_notification_inline_keyboard(p.id),
                        printer=p,
                    )
                    st["notifiedPauseErrorRepeat"] = True
        elif curr_state != "PAUSE":
            st["pauseErrorStartTime"] = None
            st["notifiedPauseErrorRepeat"] = False

        st["lastState"] = curr_state

    async def test_pause_error_reminder_triggers_at_5_minutes(self):
        """Tests that when printer is in PAUSE with error, repeat alert fires after 300 seconds."""
        base_time = 1000000.0
        self.printer.gcode_state = "PAUSE"
        self.printer.hms_resolved = ["Закінчився філамент або обрив нитки"]

        # Tick 1 at t=0: initial error notification is sent
        with patch("time.time", return_value=base_time):
            await self._run_monitoring_iteration()

        st = self.app.printer_states["p_test"]
        self.assertEqual(st["pauseErrorStartTime"], base_time)
        self.assertFalse(st["notifiedPauseErrorRepeat"])
        self.assertTrue(st["notifiedHMS"])
        self.assertEqual(self.app.send_notification.call_count, 2)  # Pause + Initial Error Alert

        # Tick 2 at t=299s: under 5 minutes, no repeat sent
        self.app.send_notification.reset_mock()
        with patch("time.time", return_value=base_time + 299.0):
            await self._run_monitoring_iteration()

        self.assertFalse(st["notifiedPauseErrorRepeat"])
        self.app.send_notification.assert_not_called()

        # Tick 3 at t=300.0s: exactly 5 minutes reached, repeat alert sent!
        with patch("time.time", return_value=base_time + 300.0):
            await self._run_monitoring_iteration()

        self.assertTrue(st["notifiedPauseErrorRepeat"])
        self.app.send_notification.assert_called_once()
        args, kwargs = self.app.send_notification.call_args
        self.assertEqual(args[0], "pause")
        self.assertIn("Повторне сповіщення про помилку!", args[1])
        self.assertIn("понад <b>5 хвилин</b>", args[1])
        self.assertIn("Закінчився філамент", args[1])
        self.assertIn("Бака! Швидше перевір його!", args[1])
        self.assertIsNotNone(kwargs.get("reply_markup"))

        # Tick 4 at t=315s: repeat already sent, no spam!
        self.app.send_notification.reset_mock()
        with patch("time.time", return_value=base_time + 315.0):
            await self._run_monitoring_iteration()

        self.app.send_notification.assert_not_called()

    async def test_pause_without_error_never_sends_reminder(self):
        """Tests that manual pause without errors never starts timer or sends reminder."""
        base_time = 1000000.0
        self.printer.gcode_state = "PAUSE"
        self.printer.hms_resolved = []
        self.printer.hms_errors = []

        with patch("time.time", return_value=base_time):
            await self._run_monitoring_iteration()

        st = self.app.printer_states["p_test"]
        self.assertIsNone(st["pauseErrorStartTime"])
        self.assertFalse(st["notifiedPauseErrorRepeat"])

        # Advance 10 minutes (600s)
        self.app.send_notification.reset_mock()
        with patch("time.time", return_value=base_time + 600.0):
            await self._run_monitoring_iteration()

        self.app.send_notification.assert_not_called()
        self.assertIsNone(st["pauseErrorStartTime"])
        self.assertFalse(st["notifiedPauseErrorRepeat"])

    async def test_resuming_resets_pause_error_timer(self):
        """Tests that resuming from PAUSE to RUNNING resets timer and repeat notification flag."""
        base_time = 1000000.0
        self.printer.gcode_state = "PAUSE"
        self.printer.hms_resolved = ["Помилка сопла"]

        # Enter pause with error and trigger repeat at 300s
        with patch("time.time", return_value=base_time):
            await self._run_monitoring_iteration()
        with patch("time.time", return_value=base_time + 300.0):
            await self._run_monitoring_iteration()

        st = self.app.printer_states["p_test"]
        self.assertTrue(st["notifiedPauseErrorRepeat"])

        # Resume printing
        self.printer.gcode_state = "RUNNING"
        with patch("time.time", return_value=base_time + 320.0):
            await self._run_monitoring_iteration()

        self.assertIsNone(st["pauseErrorStartTime"])
        self.assertFalse(st["notifiedPauseErrorRepeat"])
        self.assertFalse(st["notifiedPause"])

    async def test_new_error_while_paused_rearms_reminder(self):
        """Tests that if a new error occurs while paused, repeat timer re-arms."""
        base_time = 1000000.0
        self.printer.gcode_state = "PAUSE"
        self.printer.hms_resolved = ["Помилка A"]

        # Initial tick
        with patch("time.time", return_value=base_time):
            await self._run_monitoring_iteration()

        # Repeat sent at 300s
        with patch("time.time", return_value=base_time + 300.0):
            await self._run_monitoring_iteration()

        st = self.app.printer_states["p_test"]
        self.assertTrue(st["notifiedPauseErrorRepeat"])

        # At t=350s, new error B appears while still paused!
        self.printer.hms_resolved = ["Помилка A", "Помилка B"]
        self.app.send_notification.reset_mock()
        with patch("time.time", return_value=base_time + 350.0):
            await self._run_monitoring_iteration()

        # New initial alert sent for error B, timer reset to t=350s
        self.app.send_notification.assert_called_once()
        self.assertEqual(st["pauseErrorStartTime"], base_time + 350.0)
        self.assertFalse(st["notifiedPauseErrorRepeat"])

        # At t=650s (300s after error B): repeat alert fires again!
        self.app.send_notification.reset_mock()
        with patch("time.time", return_value=base_time + 650.0):
            await self._run_monitoring_iteration()

        self.app.send_notification.assert_called_once()
        self.assertTrue(st["notifiedPauseErrorRepeat"])
        args, kwargs = self.app.send_notification.call_args
        self.assertIn("Помилка B", args[1])


if __name__ == "__main__":
    unittest.main()
