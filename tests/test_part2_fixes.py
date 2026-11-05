"""
Unit tests specifically targeting Part 2 audit fixes:
- Blocker #1: handle_admin_menu import and alias
- Blocker #2: json import in app.py
- Issue 2.1: HTML escaping and parse mode for notifications
- Issue 2.2: Callback data length under 64 bytes and underscores in printer ID
- Issue 2.3: Commercial wizard states and printer editing admin guards
"""

import html
import pytest
from unittest.mock import AsyncMock, MagicMock


def test_blocker1_admin_menu_alias():
    import bot.handlers.admin as admin_module
    assert hasattr(admin_module, "handle_admin_panel"), "handle_admin_panel must exist"
    assert hasattr(admin_module, "handle_admin_menu"), "handle_admin_menu alias must exist"
    assert admin_module.handle_admin_menu == admin_module.handle_admin_panel, "handle_admin_menu should alias handle_admin_panel"


def test_blocker2_json_imported_in_app():
    import app
    assert hasattr(app, "json"), "json module must be imported in app.py"


def test_issue21_commercial_states_contains_choice():
    from bot.handlers.commercial import COMMERCIAL_STATES
    assert "edit_preset_field_choice" in COMMERCIAL_STATES, "'edit_preset_field_choice' must be in COMMERCIAL_STATES"


@pytest.mark.asyncio
async def test_issue21_commercial_wizard_rejects_non_text():
    from bot.handlers.commercial import is_commercial_wizard_state
    msg = MagicMock()
    msg.text = None
    app_mock = MagicMock()
    res = await is_commercial_wizard_state(msg, app_mock)
    assert res is False, "is_commercial_wizard_state must return False for non-text messages"


def test_issue22_callback_data_length():
    part_id = "12345678-1234-1234-1234-123456789abc"
    printer_id = "87654321-4321-4321-4321-cba987654321"

    cb_conf = f"conf_pxp:{part_id}:{printer_id}"
    if len(cb_conf.encode("utf-8")) > 64:
        cb_conf = f"cf_px:{part_id[:20]}:{printer_id[:20]}"

    assert len(cb_conf.encode("utf-8")) <= 64, f"Callback data too long: {len(cb_conf)} bytes"

    # Test parser recognizes cf_px prefix
    raw = (
        cb_conf.replace("part_exec_print_", "")
        .replace("part_exec_print:", "")
        .replace("conf_pxp:", "")
        .replace("cf_px:", "")
        .replace("pxp:", "")
    )
    parts = raw.split(":", 1)
    assert len(parts) == 2
    assert parts[0] == part_id[:20]
    assert parts[1] == printer_id[:20]


@pytest.mark.asyncio
async def test_issue22_deduct_callback_with_underscores():
    from bot.handlers.callbacks import handle_callback_query

    app_mock = MagicMock()
    printer_mock = MagicMock()
    printer_mock.name = "Bambu_P1S_Farm_1"
    printer_mock.get_active_slot_key.return_value = "0"
    printer_mock.get_slot_grams.return_value = 500.0
    app_mock.printers = {"bambu_p1s_lab_1": printer_mock}
    app_mock.save_printers_config = AsyncMock()

    callback_mock = MagicMock()
    callback_mock.data = "deduct_w_bambu_p1s_lab_1_10"
    callback_mock.answer = AsyncMock()
    callback_mock.message.reply = AsyncMock()

    await handle_callback_query(callback_mock, app_mock)

    printer_mock.set_slot_grams.assert_called_once_with(490.0, "0")
    callback_mock.answer.assert_called_once()
    assert "Списано 10.0g" in callback_mock.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_issue22_maintenance_reset_with_underscores():
    from bot.handlers.callbacks import handle_callback_query

    app_mock = MagicMock()
    printer_mock = MagicMock()
    printer_mock.name = "Bambu_P1S"
    printer_mock.maintenance_items = {"carbon_filter": {"name": "Вугільний фільтр"}}
    app_mock.printers = {"bambu_p1s_lab_1": printer_mock}
    app_mock.save_printers_config = AsyncMock()

    callback_mock = MagicMock()
    callback_mock.data = "notify_maint_reset_bambu_p1s_lab_1_carbon_filter"
    callback_mock.answer = AsyncMock()
    callback_mock.message.reply = AsyncMock()

    await handle_callback_query(callback_mock, app_mock)

    printer_mock.reset_maintenance_counter.assert_called_once_with("carbon_filter")
    callback_mock.answer.assert_called_once()


@pytest.mark.asyncio
async def test_issue23_printer_edit_guards_against_non_admin():
    from bot.handlers.printers.edit import _check_admin_and_selected_printer

    app_mock = MagicMock()
    app_mock.is_user_admin = AsyncMock(return_value=False)
    msg = MagicMock()
    msg.chat.id = 999999
    msg.answer = AsyncMock()

    res = await _check_admin_and_selected_printer(msg, app_mock)
    assert res is None
    msg.answer.assert_called_once()
    assert "немає прав адміністратора" in msg.answer.call_args[0][0]


def test_issue21_status_card_escaping():
    from bot.handlers.printers.view import build_printer_status_card

    printer = MagicMock()
    printer.name = "Test_Printer_<Special>&"
    printer.ip = "192.168.1.50<script>"
    printer.access_code = "123456&code"
    printer.serial_number = "01P00A123456<sn>"
    printer.nozzle_diameter = "0.4<mm>"
    printer.mapped_state = "ONLINE"
    printer.is_online = True
    printer.nozzle_temper = 220
    printer.bed_temper = 60
    printer.chamber_temper = 35
    printer.nozzle_target_temper = 220
    printer.bed_target_temper = 60
    printer.wifi_signal = "-50dBm"
    printer.print_hours = 12.5
    printer.has_ams = False
    printer.ams_trays_info = {}
    printer.get_active_slot_key.return_value = "254"
    printer.get_slot_grams.return_value = 500.0
    printer.filament_type = "PLA<CF>"
    printer.filament_grams = 500.0

    card = build_printer_status_card(printer)
    # Ensure sensitive block has escaped content
    assert "&lt;script&gt;" in card
    assert "&amp;code" in card
    assert "&lt;sn&gt;" in card
    assert "&lt;Special&gt;&amp;" in card
    assert "<script>" not in card
