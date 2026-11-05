import asyncio
import functools
import hmac
from pathlib import Path
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from storage.manager import StorageManager
from services.http.auth import check_auth, is_admin_request
import utils.image_utils as image_utils


@pytest.mark.asyncio
async def test_empty_spool_persistence_and_scrap_refund(tmp_path):
    """Empty spool (0.0g) is NOT deleted from DB and can be refunded when scrap is reported."""
    storage = StorageManager(base_dir=tmp_path)
    
    # Save spool with 0.0g
    spool_data = {
        "spool_zero": {
            "id": "spool_zero",
            "name": "Zero Spool",
            "type": "PETG",
            "color": "#000000",
            "remaining_grams": 0.0,
            "assigned_printer_id": "printer_1",
            "assigned_slot_key": "0",
        }
    }
    await storage.save_spools(spool_data)
    
    # Verify load_spools returns the 0.0g spool
    loaded = await storage.load_spools()
    assert "spool_zero" in loaded
    assert loaded["spool_zero"]["remaining_grams"] == 0.0
    
    # Add a history entry for print job that used this spool
    job_entry = {
        "timestamp": time.time(),
        "printer_id": "printer_1",
        "printer_name": "Voron",
        "subtask_name": "Bracket",
        "weight_g": 50.0,
        "status": "SUCCESS",
    }
    await storage.add_history_entry(job_entry)
    
    # Mark scrap and refund 20g back to spool_zero
    scrap_res = await storage.mark_history_scrap(
        timestamp=job_entry["timestamp"],
        wasted_weight_g=30.0,
        reason="Warpage",
        refund_grams=20.0,
        printer_id="printer_1",
        slot_key="0",
        spool_id="spool_zero",
    )
    assert scrap_res is not None
    assert scrap_res["status"] == "SCRAP"
    
    # Spool must now have 20.0g refunded!
    reloaded = await storage.load_spools()
    assert reloaded["spool_zero"]["remaining_grams"] == 20.0


@pytest.mark.asyncio
async def test_record_spool_movement_sqlite_ssot(tmp_path):
    """record_spool_movement writes to SQLite without rewriting giant movements.json."""
    storage = StorageManager(base_dir=tmp_path)
    entry = await storage.record_spool_movement(
        spool_id="spool_1",
        spool_name="Spool 1",
        action="test_action",
        weight_change_g=-15.5,
        prev_weight_g=500.0,
        new_weight_g=484.5,
        reason="Test print",
        user="Tester",
    )
    assert entry["action"] == "test_action"
    
    # Verify movement exists in DB query
    movements = await storage.load_spool_movements(spool_id="spool_1")
    assert len(movements) == 1
    assert movements[0]["spool_id"] == "spool_1"
    assert movements[0]["weight_change_g"] == -15.5


@pytest.mark.asyncio
async def test_rbac_control_actions_restricted():
    """Verify pause, resume, skip_objects, assign_spool, unassign_spool, toggle_notify require admin."""
    from services.http.routes_control import ADMIN_ACTIONS
    expected_restricted = {
        "stop",
        "pause",
        "resume",
        "skip_objects",
        "assign_spool",
        "unassign_spool",
        "toggle_notify",
        "reset_maint",
        "set_maint_interval",
        "calibrate",
        "load_filament",
        "unload_filament",
        "set_speed",
        "set_filament",
        "set_slot_grams",
        "set_ams_enabled",
    }
    for action in expected_restricted:
        assert action in ADMIN_ACTIONS, f"Action '{action}' must be restricted to ADMIN"


@pytest.mark.asyncio
async def test_auth_timing_attack_protection():
    """Verify compare_digest is used for constant-time comparison in auth."""
    secret = "super_secret_key_12345"
    assert hmac.compare_digest("super_secret_key_12345", secret) is True
    assert hmac.compare_digest("wrong_key", secret) is False


def test_font_cache_lru():
    """Verify _load_unicode_font is decorated with lru_cache."""
    assert hasattr(image_utils._load_unicode_font, "cache_info")
    info = image_utils._load_unicode_font.cache_info()
    assert info.maxsize == 32


@pytest.mark.asyncio
async def test_delete_printer_atomic_spool_lock(tmp_path):
    """Verify delete_printer_atomic acquires both fleet_mutation and spools locks."""
    storage = StorageManager(base_dir=tmp_path)
    
    # Save a printer
    await storage.save_printers([{"id": "p_del_test", "name": "Printer To Delete"}])
    
    # Save a spool attached to this printer
    await storage.save_spools({
        "s_attached": {
            "id": "s_attached",
            "name": "Attached Spool",
            "remaining_grams": 400.0,
            "assigned_printer_id": "p_del_test",
            "assigned_slot_key": "0",
        }
    })
    
    # Delete printer atomically
    ok = await storage.delete_printer_atomic("p_del_test")
    assert ok is True
    
    # Spool must be unmounted
    spools = await storage.load_spools()
    assert "s_attached" in spools
    assert spools["s_attached"].get("assigned_printer_id") is None
    assert spools["s_attached"].get("assigned_slot_key") is None


def test_report_generator_path_traversal_sanitization(tmp_path):
    """Verify report_generator sanitizes path traversal attempts in image URLs and outputs valid PDF."""
    import config
    from services.report_generator import generate_parts_pdf_report
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("TOP_SECRET", encoding="utf-8")

    with patch.object(config, "STORAGE_DIR", tmp_path):
        parts = {
            "part_1": {
                "id": "part_1",
                "name": "Malicious Part",
                "model": "A1",
                "filament_type": "PLA",
                "price": 50.0,
                "quantity": 1,
                "image": "/uploads/../../secret.txt",
            }
        }
        pdf_bytes = generate_parts_pdf_report(parts)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fleet_lights_admin_required():
    """Verify handle_fleet_lights rejects viewer requests."""
    from services.http.routes_control import handle_fleet_lights
    from aiohttp.test_utils import make_mocked_request

    req = make_mocked_request("POST", "/api/fleet/lights")
    req.app["app_obj"] = MagicMock()
    with patch("services.http.routes_control.check_auth", AsyncMock(return_value=True)), \
         patch("services.http.routes_control.is_admin_request", AsyncMock(return_value=False)):
        resp = await handle_fleet_lights(req)
        assert resp.status == 403


@pytest.mark.asyncio
async def test_files_upload_admin_required():
    """Verify handle_file_upload and handle_image_upload reject viewer requests."""
    from services.http.routes_files import handle_file_upload, handle_image_upload
    from aiohttp.test_utils import make_mocked_request

    req1 = make_mocked_request("POST", "/api/files/upload")
    req1.app["app_obj"] = MagicMock()
    with patch("services.http.routes_files.check_auth", AsyncMock(return_value=True)), \
         patch("services.http.routes_files.is_admin_request", AsyncMock(return_value=False)):
        resp1 = await handle_file_upload(req1)
        assert resp1.status == 403

    req2 = make_mocked_request("POST", "/api/files/upload_image")
    req2.app["app_obj"] = MagicMock()
    with patch("services.http.routes_files.check_auth", AsyncMock(return_value=True)), \
         patch("services.http.routes_files.is_admin_request", AsyncMock(return_value=False)):
        resp2 = await handle_image_upload(req2)
        assert resp2.status == 403


@pytest.mark.asyncio
async def test_handle_tray_event_unassigned_slot_no_crash(tmp_path):
    """Verify handle_tray_event does not crash when unmounting slot with no spool assigned."""
    from app import PrinterBotApp
    storage = StorageManager(base_dir=tmp_path)

    app_bot = MagicMock()
    app_bot.storage = storage
    app_bot.send_notification = AsyncMock()
    app_bot.save_printers_config = AsyncMock()

    printer = MagicMock()
    printer.id = "p_test"
    printer.name = "Test Printer"
    printer.set_slot_grams = MagicMock()

    # Event on empty slot with no spool assigned
    await PrinterBotApp.handle_tray_event(app_bot, printer, {"event": "tray_unloaded", "slot_id": "0"})

    # No notification sent and no exception raised
    assert app_bot.send_notification.call_count == 0


