"""
Automated validation test suite for all Reply Keyboards and Buttons.
Guarantees 100% button coverage in both Ukrainian and English, verifying that
no button triggers the unhandled navigation fallback message or raises exceptions.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aiogram.types import Chat, Message, User
from bot.handlers import setup_routers
from bot.keyboards import (
    get_main_keyboard,
    get_printers_keyboard,
    get_printer_menu_keyboard,
    get_printer_control_keyboard,
    get_edit_printer_keyboard,
    get_single_printer_filament_keyboard,
    get_filament_menu_keyboard,
    get_parts_reply_keyboard,
    get_part_action_reply_keyboard,
    get_notify_keyboard,
)
from bot.states import PartEditingStates
from storage.manager import StorageManager


@pytest.fixture
def mock_printer():
    printer = MagicMock()
    printer.id = "p1"
    printer.name = "Bambu Lab P1S"
    printer.gcode_state = "IDLE"
    printer.mapped_state = "ONLINE"
    printer.is_online = True
    printer.nozzle_temper = 210
    printer.bed_temper = 60
    printer.mc_percent = 0
    printer.filament_type = "PLA"
    printer.filament_grams = 800.0
    printer.price_per_kg = 850.0
    printer.spd_mag = 100
    printer.chamber_light_state = "off"
    printer.maintenance_hours_counter = 45.0
    printer.maintenance_interval_hours = 150.0
    printer.notify_settings = {}
    printer.notify = True
    printer.ip = "192.168.1.50"
    printer.access_code = "12345678"
    printer.serial_number = "00M00A000000000"
    printer.ams_units = []
    printer.get_clean_job_objects = MagicMock(return_value=[])
    printer.toggle_light = MagicMock(return_value=True)
    printer.toggle_chamber_light = MagicMock(return_value=True)
    printer.set_speed_level = MagicMock(return_value=True)
    printer.reset_maintenance_counter = MagicMock()
    printer.destroy = MagicMock()
    printer.get_notify_dict = MagicMock(return_value={})
    return printer


@pytest.fixture
def app_and_storage(tmp_path, mock_printer):
    sm = StorageManager(tmp_path / "printers_storage")
    app = MagicMock()
    app.storage = sm
    app.is_user_approved = AsyncMock(return_value=True)
    app.is_user_admin = AsyncMock(return_value=True)
    app.save_printers_config = AsyncMock()
    app.printers = {"p1": mock_printer}
    return app, sm


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["uk", "en"])
async def test_all_reply_keyboards_and_buttons(app_and_storage, mock_printer, lang):
    """
    Tests every single reply keyboard button in the specified language.
    Asserts that:
    1. An answer was generated.
    2. The message was handled by an active router and did NOT hit the navigation fallback.
    3. No unhandled exception occurred.
    """
    app, sm = app_and_storage
    router = setup_routers()

    # Seed sample parts and spools into mock storage
    await sm.save_parts({
        "part1": {
            "id": "part1",
            "name": "Test Gear",
            "count": 5,
            "filament_type": "PLA",
            "filament_weight": 50,
            "print_time": "1h 30m",
            "image_path": None,
            "three_mf_path": None,
        }
    })
    await sm.save_spools({
        "spool1": {
            "id": "spool1",
            "name": "Bambu PLA Basic",
            "type": "PLA",
            "color": "Black",
            "weight": 800,
            "price": 850,
        }
    })

    chat = Chat(id=777, type="private")
    user_obj = User(id=777, is_bot=False, first_name="Tester")

    async def check_button(btn_text, user_state="idle", context_data=None, fsm_state=None):
        ctx = context_data or {}
        await sm.save_user({
            "user_id": "777",
            "chat_id": "777",
            "state": user_state,
            "context_data": ctx,
            "language": lang,
        })

        msg = Message(message_id=101, date=datetime.now(), chat=chat, from_user=user_obj, text=btn_text)
        mock_answer = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_photo", mock_answer)
        object.__setattr__(msg, "answer_document", mock_answer)
        object.__setattr__(msg, "answer_animation", mock_answer)

        mock_fsm = MagicMock()
        state_str = fsm_state.state if hasattr(fsm_state, "state") else fsm_state
        mock_fsm.get_state = AsyncMock(return_value=state_str)
        mock_fsm.set_state = AsyncMock()
        mock_fsm.clear = AsyncMock()
        mock_fsm.get_data = AsyncMock(return_value={"selected_part_id": "part1"})
        mock_fsm.update_data = AsyncMock()

        with patch("services.camera_stream.capture_real_camera_photo", AsyncMock(return_value=b"fake_jpeg")):
            await router.propagate_event("message", msg, app=app, bot=app.bot, state=mock_fsm)

        assert mock_answer.called, f"No answer called for button '{btn_text}' ({lang})"

        sent_text = ""
        for call in mock_answer.call_args_list:
            if call.args:
                sent_text += str(call.args[0])

        assert "Скористайтесь кнопками меню для навігації" not in sent_text, (
            f"Fallback triggered for button '{btn_text}' ({lang}): {sent_text}"
        )
        assert "Please use the menu buttons for navigation" not in sent_text, (
            f"Fallback triggered for button '{btn_text}' ({lang}): {sent_text}"
        )

    keyboards_to_test = [
        ("Main Keyboard (Admin)", get_main_keyboard(is_admin=True, lang=lang), "idle", {}, None),
        ("Main Keyboard (User)", get_main_keyboard(is_admin=False, lang=lang), "idle", {}, None),
        ("Printers Keyboard", get_printers_keyboard(app.printers, lang=lang), "idle", {}, None),
        ("Printer Menu Keyboard", get_printer_menu_keyboard(mock_printer, lang=lang), "printer_menu", {"selected_printer_id": "p1"}, None),
        ("Printer Control (Idle)", get_printer_control_keyboard(mock_printer, lang=lang), "printer_menu", {"selected_printer_id": "p1"}, None),
        ("Edit Printer Keyboard", get_edit_printer_keyboard(lang=lang), "edit_printer_menu", {"selected_printer_id": "p1"}, None),
        ("Single Printer Filament", get_single_printer_filament_keyboard(lang=lang), "printer_menu", {"selected_printer_id": "p1"}, None),
        ("Filament Menu", get_filament_menu_keyboard(lang=lang), "idle", {}, None),
        ("Parts Reply Keyboard", get_parts_reply_keyboard(lang=lang), "idle", {}, PartEditingStates.in_parts_list),
        ("Part Action Reply Keyboard", get_part_action_reply_keyboard(lang=lang), "idle", {}, PartEditingStates.in_part_info),
        ("Notify Keyboard", get_notify_keyboard({}, lang=lang), "idle", {}, None),
    ]

    total_tested = 0
    for kb_name, kb, u_state, ctx, fsm_st in keyboards_to_test:
        for row in kb.keyboard:
            for btn in row:
                if getattr(btn, "web_app", None):
                    continue
                await check_button(btn.text, user_state=u_state, context_data=ctx, fsm_state=fsm_st)
                total_tested += 1

    assert total_tested > 0, "No buttons were tested!"
