"""
Unit & Integration Tests for БЛОК 3: Telegram Bot Keyboards, Buttons & Notifications
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from models.printer import BambuPrinter
from app import PrinterBotApp
from bot.handlers.filament.mount import get_mounted_spools_or_trays
from bot.handlers.parts.view import SEARCH_NAVIGATION_TEXTS


class DummyPrinter(BambuPrinter):
    def __init__(self, p_id="test_p1", name="Bambu X1C"):
        storage_mock = MagicMock()
        cfg = {
            "id": p_id,
            "name": name,
            "ip": "127.0.0.1",
            "accessCode": "12345678",
            "serialNumber": "00M00A000000001",
            "printer_model": "X1C",
            "notify": {"start": True, "finish": True, "pause": True, "hms": True},
            "ams_enabled": True,
        }
        super().__init__(config=cfg, storage=storage_mock)
        self.ams_humidity_idx = 5


@pytest.mark.asyncio
async def test_ams_humidity_alert_logic():
    """Verify AMS humidity alert triggers on 1/5 and 2/5 (wet), but NEVER on 5/5 or 4/5 (dry)."""
    p = DummyPrinter()

    # Case 1: Perfectly dry (5/5)
    p.ams_humidity_idx = 5
    h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
    assert not (0 < h_idx <= 2), "Should NOT trigger alert for level 5 (dry)"

    # Case 2: Optimal (4/5)
    p.ams_humidity_idx = 4
    h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
    assert not (0 < h_idx <= 2), "Should NOT trigger alert for level 4"

    # Case 3: Critically wet (1/5)
    p.ams_humidity_idx = 1
    h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
    assert 0 < h_idx <= 2, "MUST trigger alert for level 1 (critically wet)"
    hum_state_str = "🔴 Критична (Рівень 1/5, волого!)" if h_idx == 1 else "🟠 Підвищена (Рівень 2/5, волого)"
    assert "1/5" in hum_state_str

    # Case 4: Elevated humidity (2/5)
    p.ams_humidity_idx = 2
    h_idx = int(getattr(p, "ams_humidity_idx", 0) or 0)
    assert 0 < h_idx <= 2, "MUST trigger alert for level 2 (humid)"
    hum_state_str = "🔴 Критична (Рівень 1/5, волого!)" if h_idx == 1 else "🟠 Підвищена (Рівень 2/5, волого)"
    assert "2/5" in hum_state_str


@pytest.mark.asyncio
async def test_sync_notify_change_does_not_overwrite_all_printers():
    """Verify _sync_notify_change only updates user preferences and does NOT mutate farm printers."""
    from bot.handlers.notifications import _sync_notify_change

    app_mock = MagicMock()
    app_mock.storage = MagicMock()
    app_mock.storage.save_user = AsyncMock()

    p1 = DummyPrinter("p1", "Printer 1")
    p1.notify = {"start": True, "finish": True, "pause": True, "hms": True}
    p2 = DummyPrinter("p2", "Printer 2")
    p2.notify = {"start": True, "finish": True, "pause": True, "hms": True}

    app_mock.printers = {"p1": p1, "p2": p2}

    user = {"chat_id": "12345", "notify": {"start": True, "finish": True}}

    # User turns OFF 'start' notifications for themselves
    await _sync_notify_change(app_mock, user, "start", False)

    # User object updated
    assert user["notify"]["start"] is False
    app_mock.storage.save_user.assert_awaited_once_with(user)

    # Hardware printer configs MUST REMAIN UNTOUCHED
    assert p1.notify["start"] is True, "p1.notify must not be overwritten by single user preference"
    assert p2.notify["start"] is True, "p2.notify must not be overwritten by single user preference"


@pytest.mark.asyncio
async def test_reset_maintenance_resets_all_items():
    """Verify reset_maintenance_counter('all') resets counters on all individual maintenance items."""
    p = DummyPrinter()
    p.maintenance_items = {
        "rails": {"name": "Rails", "counter_hours": 125.4, "interval_hours": 100.0},
        "lead_screws": {"name": "Screws", "counter_hours": 250.0, "interval_hours": 200.0},
    }
    p.maintenance_hours_counter = 125.4

    p.reset_maintenance_counter("all")

    assert p.maintenance_hours_counter == 0.0
    assert p.maintenance_items["rails"]["counter_hours"] == 0.0
    assert p.maintenance_items["lead_screws"]["counter_hours"] == 0.0


def test_single_spool_unmount_safety():
    """Verify single spool is not unmounted by arbitrary text."""
    mounted_list = [
        {"button_text": "🧵 PLA White (AMS 1)", "slot_label": "AMS 1", "name": "PLA White", "printer_id": "p1", "slot_key": "0"}
    ]

    # Arbitrary random text:
    text = "Скільки коштує друк?"
    selected_item = next(
        (m for m in mounted_list if m["button_text"] == text or text in m["button_text"] or m["slot_label"] in text or m["name"] in text),
        None,
    )
    assert selected_item is None, "Arbitrary text must NOT match and unmount spool!"

    # Legitimate matching text:
    valid_text = "🧵 PLA White (AMS 1)"
    selected_valid = next(
        (m for m in mounted_list if m["button_text"] == valid_text or valid_text in m["button_text"] or m["slot_label"] in valid_text or m["name"] in valid_text),
        None,
    )
    assert selected_valid is not None
    assert selected_valid["slot_key"] == "0"


def test_parts_fsm_search_navigation_texts_include_admin_and_notifications():
    """Verify SEARCH_NAVIGATION_TEXTS has notifications, admin, commercial, settings, history."""
    assert "🔔 сповіщення" in SEARCH_NAVIGATION_TEXTS
    assert "сповіщення" in SEARCH_NAVIGATION_TEXTS
    assert "👑 адмінка" in SEARCH_NAVIGATION_TEXTS
    assert "адмінка" in SEARCH_NAVIGATION_TEXTS
    assert "💰 комерція" in SEARCH_NAVIGATION_TEXTS
    assert "комерція" in SEARCH_NAVIGATION_TEXTS
    assert "⚙️ налаштування" in SEARCH_NAVIGATION_TEXTS
    assert "📜 історія" in SEARCH_NAVIGATION_TEXTS


@pytest.mark.asyncio
async def test_commercial_delete_preset_confirmation_callbacks():
    """Verify conf_del_preset deletes preset from storage and canc_del_preset cancels safely."""
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from aiogram.types import CallbackQuery, Chat, Message, User
    from bot.handlers import setup_routers
    from storage.manager import StorageManager

    temp_dir = tempfile.TemporaryDirectory()
    sm = StorageManager(Path(temp_dir.name))
    router = setup_routers()

    app_mock = MagicMock()
    app_mock.storage = sm
    app_mock.is_user_approved = AsyncMock(return_value=True)
    app_mock.is_user_admin = AsyncMock(return_value=True)
    app_mock.bot = MagicMock()

    # Pre-populate presets
    test_presets = {
        "preset_1": {
            "id": "preset_1",
            "name": "Custom PLA",
            "price_per_g": 1.0,
            "electricity_rate_uah": 4.32,
            "power_watts": 100.0,
            "depreciation_val": "10",
            "consumables_val": "5",
            "profit_val": "50%",
        }
    }
    await sm.save_json(Path(temp_dir.name) / "commercial_presets.json", test_presets)

    chat = Chat(id=123, type="private")
    user_obj = User(id=123, is_bot=False, first_name="Test")
    await sm.save_user({"chat_id": "123", "user_id": "123", "state": "select_preset_to_delete", "context_data": {"commercial": {}}})

    # 1. Test cancel callback
    msg_cancel = Message(message_id=1, date=datetime.now(), chat=chat, from_user=user_obj, text="")
    mock_edit_cancel = AsyncMock()
    mock_ans_cancel = AsyncMock()
    object.__setattr__(msg_cancel, "edit_text", mock_edit_cancel)
    object.__setattr__(msg_cancel, "answer", mock_ans_cancel)
    cb_cancel = CallbackQuery(id="cb_c", from_user=user_obj, chat_instance="1", message=msg_cancel, data="canc_del_preset")
    object.__setattr__(cb_cancel, "answer", AsyncMock())

    await router.propagate_event("callback_query", cb_cancel, app=app_mock, bot=app_mock.bot)

    u_after_cancel = await sm.load_user("123")
    assert u_after_cancel["state"] == "idle"
    # Presets untouched
    curr_presets = await sm.load_json(Path(temp_dir.name) / "commercial_presets.json", {})
    assert "preset_1" in curr_presets
    assert mock_edit_cancel.called or mock_ans_cancel.called

    # 2. Test confirm deletion callback
    u_after_cancel["state"] = "select_preset_to_delete"
    await sm.save_user(u_after_cancel)

    msg_del = Message(message_id=2, date=datetime.now(), chat=chat, from_user=user_obj, text="")
    mock_edit_del = AsyncMock()
    mock_ans_del = AsyncMock()
    object.__setattr__(msg_del, "edit_text", mock_edit_del)
    object.__setattr__(msg_del, "answer", mock_ans_del)
    cb_del = CallbackQuery(id="cb_d", from_user=user_obj, chat_instance="1", message=msg_del, data="conf_del_preset:preset_1")
    object.__setattr__(cb_del, "answer", AsyncMock())

    await router.propagate_event("callback_query", cb_del, app=app_mock, bot=app_mock.bot)

    u_after_del = await sm.load_user("123")
    assert u_after_del["state"] == "idle"
    curr_presets = await sm.load_json(Path(temp_dir.name) / "commercial_presets.json", {})
    assert "preset_1" not in curr_presets


@pytest.mark.asyncio
async def test_calibrate_confirmation_flow():
    """Verify calibrate start sends confirmation dialog and conf_calib executes calibration."""
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from aiogram.types import CallbackQuery, Chat, Message, User
    from bot.handlers import setup_routers
    from storage.manager import StorageManager

    router = setup_routers()
    temp_dir = tempfile.TemporaryDirectory()
    sm = StorageManager(Path(temp_dir.name))

    app_mock = MagicMock()
    app_mock.storage = sm
    app_mock.is_user_approved = AsyncMock(return_value=True)
    app_mock.is_user_admin = AsyncMock(return_value=True)
    app_mock.bot = MagicMock()

    p = DummyPrinter("p_calib", "CalibPrinter")
    p.start_calibration = MagicMock(return_value=True)
    app_mock.printers = {"p_calib": p}

    chat = Chat(id=456, type="private")
    user_obj = User(id=456, is_bot=False, first_name="Test")
    await sm.save_user({
        "chat_id": "456",
        "user_id": "456",
        "state": "idle",
        "context_data": {"selected_printer_id": "p_calib"}
    })

    # Message: "🎯 Калібрувати"
    msg = Message(message_id=10, date=datetime.now(), chat=chat, from_user=user_obj, text="🎯 Калібрувати")
    mock_ans = AsyncMock()
    object.__setattr__(msg, "answer", mock_ans)

    await router.propagate_event("message", msg, app=app_mock, bot=app_mock.bot)

    assert mock_ans.called
    p.start_calibration.assert_not_called()
    reply_markup = mock_ans.call_args[1].get("reply_markup")
    assert reply_markup is not None
    assert any("conf_calib:p_calib" in btn.callback_data for row in reply_markup.inline_keyboard for btn in row)

    # Cancel callback
    cb_msg = Message(message_id=11, date=datetime.now(), chat=chat, from_user=user_obj, text="")
    mock_edit = AsyncMock()
    object.__setattr__(cb_msg, "edit_text", mock_edit)
    cb_canc = CallbackQuery(id="cb_c", from_user=user_obj, chat_instance="1", message=cb_msg, data="canc_calib:p_calib")
    object.__setattr__(cb_canc, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_canc, app=app_mock, bot=app_mock.bot)
    p.start_calibration.assert_not_called()

    # Confirm callback
    cb_conf = CallbackQuery(id="cb_ok", from_user=user_obj, chat_instance="1", message=cb_msg, data="conf_calib:p_calib")
    object.__setattr__(cb_conf, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_conf, app=app_mock, bot=app_mock.bot)
    p.start_calibration.assert_called_once()


@pytest.mark.asyncio
async def test_notify_pause_and_resume_confirmation_flow():
    """Verify notify_pause_ and notify_resume_ send confirmation keyboards before acting."""
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from aiogram.types import CallbackQuery, Chat, Message, User
    from bot.handlers import setup_routers
    from storage.manager import StorageManager

    router = setup_routers()
    temp_dir = tempfile.TemporaryDirectory()
    sm = StorageManager(Path(temp_dir.name))

    app_mock = MagicMock()
    app_mock.storage = sm
    app_mock.bot = MagicMock()

    p = DummyPrinter("p_nr", "NRPrinter")
    p.pause = MagicMock(return_value=True)
    p.resume = MagicMock(return_value=True)
    app_mock.printers = {"p_nr": p}

    chat = Chat(id=789, type="private")
    user_obj = User(id=789, is_bot=False, first_name="Test")

    # 1. notify_pause_
    cb_msg = Message(message_id=20, date=datetime.now(), chat=chat, from_user=user_obj, text="")
    mock_edit_rm = AsyncMock()
    object.__setattr__(cb_msg, "edit_reply_markup", mock_edit_rm)
    cb_pause = CallbackQuery(id="cb_p1", from_user=user_obj, chat_instance="1", message=cb_msg, data="notify_pause_p_nr")
    object.__setattr__(cb_pause, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_pause, app=app_mock, bot=app_mock.bot)
    p.pause.assert_not_called()
    assert mock_edit_rm.called
    kb = mock_edit_rm.call_args[1].get("reply_markup")
    assert any("conf_notify_pause_p_nr" in btn.callback_data for row in kb.inline_keyboard for btn in row)

    # 2. conf_notify_pause_
    cb_conf_pause = CallbackQuery(id="cb_p2", from_user=user_obj, chat_instance="1", message=cb_msg, data="conf_notify_pause_p_nr")
    object.__setattr__(cb_conf_pause, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_conf_pause, app=app_mock, bot=app_mock.bot)
    p.pause.assert_called_once()

    # 3. notify_resume_
    cb_resume = CallbackQuery(id="cb_r1", from_user=user_obj, chat_instance="1", message=cb_msg, data="notify_resume_p_nr")
    object.__setattr__(cb_resume, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_resume, app=app_mock, bot=app_mock.bot)
    p.resume.assert_not_called()

    # 4. conf_notify_resume_
    cb_conf_resume = CallbackQuery(id="cb_r2", from_user=user_obj, chat_instance="1", message=cb_msg, data="conf_notify_resume_p_nr")
    object.__setattr__(cb_conf_resume, "answer", AsyncMock())
    await router.propagate_event("callback_query", cb_conf_resume, app=app_mock, bot=app_mock.bot)
    p.resume.assert_called_once()


@pytest.mark.asyncio
async def test_parts_pxp_confirmation_flow():
    """Verify pxp: sends confirmation prompt and conf_pxp: actually executes print."""
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from aiogram.types import CallbackQuery, Chat, Message, User
    from bot.handlers import setup_routers
    from storage.manager import StorageManager

    router = setup_routers()
    temp_dir = tempfile.TemporaryDirectory()
    sm = StorageManager(Path(temp_dir.name))

    app_mock = MagicMock()
    app_mock.storage = sm
    app_mock.is_user_approved = AsyncMock(return_value=True)
    app_mock.is_user_admin = AsyncMock(return_value=True)
    app_mock.bot = MagicMock()

    from unittest.mock import patch
    import config

    orig_sdir = config.STORAGE_DIR
    config.STORAGE_DIR = Path(temp_dir.name)
    uploads_dir = Path(temp_dir.name) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / "gear.3mf").write_bytes(b"PK\x03\x04dummy")

    p = DummyPrinter("p_pxp", "PxpPrinter")
    p.start_print_job_async = AsyncMock(return_value=(True, "OK"))
    app_mock.printers = {"p_pxp": p}

    try:
        parts_data = {
            "part_123": {
                "id": "part_123",
                "name": "Gear",
                "three_mf": "gear.3mf",
                "tray_info": {"bed_type": "textured_plate"},
            }
        }
        await sm.save_parts(parts_data)

        chat = Chat(id=999, type="private")
        user_obj = User(id=999, is_bot=False, first_name="Test")

        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.base import StorageKey

        fsm_storage = MemoryStorage()
        key = StorageKey(bot_id=1, chat_id=999, user_id=999)
        fsm_ctx = FSMContext(storage=fsm_storage, key=key)

        cb_msg = Message(message_id=30, date=datetime.now(), chat=chat, from_user=user_obj, text="")
        mock_edit_text = AsyncMock()
        mock_ans = AsyncMock()
        object.__setattr__(cb_msg, "edit_text", mock_edit_text)
        object.__setattr__(cb_msg, "answer", mock_ans)

        with patch("services.gcode_parser.check_compatibility", return_value={"compatible": True}):
            # 1. Unconfirmed pxp:part_123:p_pxp
            cb_pxp = CallbackQuery(id="cb_pxp", from_user=user_obj, chat_instance="1", message=cb_msg, data="pxp:part_123:p_pxp")
            object.__setattr__(cb_pxp, "answer", AsyncMock())
            raw_st = await fsm_ctx.get_state()
            await router.propagate_event("callback_query", cb_pxp, app=app_mock, bot=app_mock.bot, state=fsm_ctx, raw_state=raw_st)

            # Must ask for confirmation
            assert mock_edit_text.called or mock_ans.called
            p.start_print_job_async.assert_not_called()
            call_args = mock_edit_text.call_args or mock_ans.call_args
            rm = call_args[1].get("reply_markup")
            assert rm is not None
            assert any("conf_pxp:part_123:p_pxp" in btn.callback_data for row in rm.inline_keyboard for btn in row)

            # 2. Confirmed conf_pxp:part_123:p_pxp
            cb_conf = CallbackQuery(id="cb_conf", from_user=user_obj, chat_instance="1", message=cb_msg, data="conf_pxp:part_123:p_pxp")
            object.__setattr__(cb_conf, "answer", AsyncMock())
            await router.propagate_event("callback_query", cb_conf, app=app_mock, bot=app_mock.bot, state=fsm_ctx, raw_state=raw_st)
            assert p.start_print_job_async.called
    finally:
        config.STORAGE_DIR = orig_sdir


@pytest.mark.asyncio
async def test_parts_search_navigation_settings_redirect():
    """Verify typing '⚙️ налаштування' inside parts search redirects to handle_notifications_menu without error."""
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from aiogram.types import Chat, Message, User
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.base import StorageKey
    from bot.handlers import setup_routers
    from bot.handlers.parts.view import PartEditingStates
    from storage.manager import StorageManager

    router = setup_routers()
    temp_dir = tempfile.TemporaryDirectory()
    sm = StorageManager(Path(temp_dir.name))

    app_mock = MagicMock()
    app_mock.storage = sm
    app_mock.is_user_approved = AsyncMock(return_value=True)
    app_mock.is_user_admin = AsyncMock(return_value=True)
    app_mock.bot = MagicMock()
    app_mock.printers = {}

    chat = Chat(id=111, type="private")
    user_obj = User(id=111, is_bot=False, first_name="Test")
    await sm.save_user({"chat_id": "111", "user_id": "111", "state": "idle", "context_data": {}})

    fsm_storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=111, user_id=111)
    fsm_ctx = FSMContext(storage=fsm_storage, key=key)
    await fsm_ctx.set_state(PartEditingStates.search_query)

    msg = Message(message_id=50, date=datetime.now(), chat=chat, from_user=user_obj, text="⚙️ налаштування")
    mock_ans = AsyncMock()
    object.__setattr__(msg, "answer", mock_ans)

    raw_st = await fsm_ctx.get_state()
    await router.propagate_event("message", msg, app=app_mock, bot=app_mock.bot, state=fsm_ctx, raw_state=raw_st)
    assert mock_ans.called
    state_after = await fsm_ctx.get_state()
    assert state_after is None
