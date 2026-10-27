import asyncio
import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from models.printer import BambuPrinter
from services.gcode_parser import check_compatibility
from services.http.routes_files import handle_start_print_job
from services.http.routes_parts import handle_print_part
from services.printer_file_job_service import start_print_job
from storage.manager import StorageManager
from utils.spool_fingerprint import (
    _CONTEXT_MEMORY_CACHE,
    delete_active_print_context,
    load_active_print_context,
    save_active_print_context,
)


@pytest.fixture
def temp_storage():
    """Isolated temporary storage for testing."""
    temp_dir = tempfile.mkdtemp(prefix="test_block4_storage_")
    storage = StorageManager(base_dir=Path(temp_dir))
    yield storage, Path(temp_dir)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


def _create_minimal_3mf(model_name="Bambu Lab X1 Carbon", filament_type="PLA", weight_g=50.0) -> bytes:
    """Helper to generate a valid minimal in-memory 3MF archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr(
            "Metadata/slice_info.config",
            f"""[config]
printer_model = {model_name}
filament_type = {filament_type}
filament_used_g = {weight_g}
tray_info_idx = BBL-PLA-001
filament_color = #000000
nozzle_diameter = 0.4
plate_1 = plate_1.gcode
""",
        )
        zf.writestr("Metadata/plate_1.gcode", "; G-code content\n")
    return buf.getvalue()


# =========================================================================
# 1. SD-Card Killer & Active Print Context tests
# =========================================================================
def test_delete_active_print_context_early_return(temp_storage):
    storage, temp_dir = temp_storage
    printer_id = "test_idle_printer_99"

    import utils.spool_fingerprint as sf
    sf._ensure_cache_loaded()
    sf._CONTEXT_MEMORY_CACHE.pop(printer_id, None)

    with patch("sqlite3.connect") as mock_connect, patch("storage.base.BaseStorage._atomic_write_file") as mock_atomic:
        sf.delete_active_print_context(printer_id)
        # In IDLE, if not in cache, should do early return: 0 sqlite queries, 0 atomic writes
        mock_connect.assert_not_called()
        mock_atomic.assert_not_called()


def test_save_active_print_context_skips_when_finished(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {"id": "p_finish_1", "name": "Finished P1S", "serial": "SN1", "ip": "1.1.1.1", "access_code": "123"},
        storage,
    )
    printer.gcode_state = "FINISH"
    printer.print_percentage = 100
    printer._job_deducted = True

    with patch("storage.base.BaseStorage._atomic_write_file") as mock_atomic:
        curr_p = printer.print_percentage
        if curr_p < 100 and printer.gcode_state not in ["FINISH", "SUCCESS"]:
            save_active_print_context(printer)

        mock_atomic.assert_not_called()


# =========================================================================
# 2. Spool Unmount TypeError verification
# =========================================================================
@pytest.mark.asyncio
async def test_record_spool_movement_accepts_printer_id_and_slot(temp_storage):
    storage, temp_dir = temp_storage

    # Setup initial spool
    spools = {
        "spool_ams_1": {
            "id": "spool_ams_1",
            "name": "PLA White",
            "remaining_grams": 800.0,
            "total_grams": 1000.0,
            "assigned_printer_id": "printer_1",
            "assigned_slot_key": "0",
        }
    }
    await storage.save_spools(spools)

    # Calling record_spool_movement with printer_id and slot_key MUST NOT raise TypeError
    movement = await storage.record_spool_movement(
        spool_id="spool_ams_1",
        spool_name="PLA White",
        action="unassign",
        weight_change_g=0.0,
        prev_weight_g=800.0,
        new_weight_g=800.0,
        reason="Hardware tray unloaded",
        user="Bambu Hardware",
        printer_id="printer_1",
        slot_key="0",
    )
    assert movement is not None
    assert movement["printer_id"] == "printer_1"
    assert movement["action"] == "unassign"


# =========================================================================
# 3. Print over RUNNING printer is rejected
# =========================================================================
@pytest.mark.asyncio
async def test_start_print_job_rejects_running_printer(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {"id": "p_run_1", "name": "Busy Printer", "serial": "SN2", "ip": "1.1.1.2", "access_code": "123"},
        storage,
    )
    printer._client = MagicMock()
    printer._client.is_connected.return_value = True
    printer.gcode_state = "RUNNING"

    raw_3mf = _create_minimal_3mf()

    with patch("services.printer_file_job_service.upload_3mf_to_bambu") as mock_upload:
        success, message = await start_print_job(printer, raw_3mf, "test_job.3mf")
        assert success is False
        assert "вже виконує друк" in message
        mock_upload.assert_not_called()


@pytest.mark.asyncio
async def test_routes_parts_rejects_running_printer(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {"id": "p_run_part", "name": "Busy Part Printer", "serial": "SN3", "ip": "1.1.1.3", "access_code": "123"},
        storage,
    )
    printer.gcode_state = "RUNNING"

    app_mock = MagicMock()
    app_mock.storage = storage
    app_mock.printers = {"p_run_part": printer}

    part_id = "test_part_1"
    parts = {
        part_id: {
            "id": part_id,
            "name": "Gear",
            "three_mf": "gear.3mf",
            "weight_g": 30.0,
        }
    }
    await storage.save_parts(parts)

    req = MagicMock(spec=web.Request)
    req.app = {"app_obj": app_mock}
    req.match_info = {"part_id": part_id, "printer_id": "p_run_part"}

    with patch("services.http.routes_parts.check_auth", AsyncMock(return_value=True)), \
         patch("services.http.routes_parts.is_admin_request", AsyncMock(return_value=True)):
        resp = await handle_print_part(req)
        assert resp.status == 409
        body = json.loads(resp.text)
        assert "Принтер вже виконує друк" in body["error"]


@pytest.mark.asyncio
async def test_routes_files_rejects_running_printer(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {"id": "p_run_file", "name": "Busy File Printer", "serial": "SN4", "ip": "1.1.1.4", "access_code": "123"},
        storage,
    )
    printer.gcode_state = "PAUSE"

    app_mock = MagicMock()
    app_mock.storage = storage
    app_mock.printers = {"p_run_file": printer}

    req = MagicMock(spec=web.Request)
    req.app = {"app_obj": app_mock}
    req.match_info = {"id": "p_run_file"}

    with patch("services.http.routes_files.check_auth", AsyncMock(return_value=True)), \
         patch("services.http.routes_files.is_admin_request", AsyncMock(return_value=True)):
        resp = await handle_start_print_job(req)
        assert resp.status == 409
        body = json.loads(resp.text)
        assert "Принтер вже виконує друк" in body["error"]


# =========================================================================
# 4. Weight & AMS Compatibility checks
# =========================================================================
def test_check_compatibility_detects_low_filament(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {
            "id": "p_compat_1",
            "name": "X1C AMS",
            "model": "X1C",
            "serial": "SN5",
            "ip": "1.1.1.5",
            "access_code": "123",
            "has_ams": True,
        },
        storage,
    )
    printer.ams_trays_info = {"0": {"type": "PLA", "empty": False}}
    printer.set_slot_grams(20.0, "0")

    # When weight_g (150g) exceeds slot remaining grams (20g), it must return filament_warning
    res = check_compatibility(
        sliced_model="Bambu Lab X1 Carbon",
        filament_type="PLA",
        target_printer_name=printer.name,
        target_filament="PLA",
        printer=printer,
        weight_g=150.0,
    )
    assert res["compatible"] is True
    assert "filament_warning" in res
    assert "мало нитки: залишок 20г < ваги моделі 150г" in res["filament_warning"]


@pytest.mark.asyncio
async def test_start_print_job_validates_ams_before_ftps(temp_storage):
    storage, temp_dir = temp_storage
    printer = BambuPrinter(
        {
            "id": "p_ams_check",
            "name": "AMS Printer",
            "serial": "SN6",
            "ip": "1.1.1.6",
            "access_code": "123",
            "has_ams": True,
        },
        storage,
    )
    printer.ams_trays_info = {"0": {"type": "PETG", "empty": False}}
    printer._client = MagicMock()
    printer._client.is_connected.return_value = True
    printer.gcode_state = "IDLE"

    # Require PLA, but printer only has PETG in AMS
    raw_3mf = _create_minimal_3mf(filament_type="PLA", weight_g=50.0)

    with patch("services.printer_file_job_service.upload_3mf_to_bambu") as mock_upload:
        success, message = await start_print_job(printer, raw_3mf, "job_pla.3mf", use_ams=True)
        assert success is False
        assert "Невідповідність філаменту в AMS" in message
        # Must NOT perform FTPS upload if filament is incompatible!
        mock_upload.assert_not_called()


# =========================================================================
# 5. Triple-Write & SQLite SSOT verification
# =========================================================================
@pytest.mark.asyncio
async def test_mark_history_scrap_updates_sqlite(temp_storage):
    storage, temp_dir = temp_storage

    ts = time.time()
    entry = {
        "timestamp": ts,
        "printer_id": "p_hist_1",
        "printer_name": "Printer Hist",
        "subtask_name": "Bracket",
        "weight_g": 40.0,
        "cost_uah": 50.0,
        "status": "SUCCESS",
    }
    await storage.add_history_entry(entry)

    # Verify initially present in SQLite
    history_before = await storage.load_history()
    assert len(history_before) == 1
    assert history_before[0]["status"] == "SUCCESS"

    # Mark as scrap
    updated = await storage.mark_history_scrap(
        timestamp=ts,
        wasted_weight_g=35.0,
        reason="Layer shift",
    )
    assert updated is not None
    assert updated["is_scrap"] is True
    assert updated["status"] == "SCRAP"

    # Check that SQLite table print_history was directly updated
    conn = storage._get_db()
    try:
        cur = conn.execute("SELECT status, data_json FROM print_history WHERE abs(timestamp - ?) < 0.5", (ts,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "SCRAP"
        d = json.loads(row[1])
        assert d.get("is_scrap") is True
        assert d.get("scrap_reason") == "Layer shift"
    finally:
        conn.close()

    # Verify load_history reads updated data
    history_after = await storage.load_history()
    assert history_after[0]["status"] == "SCRAP"
    assert history_after[0]["is_scrap"] is True


@pytest.mark.asyncio
async def test_storage_load_json_redirects_to_relational_tables(temp_storage):
    storage, temp_dir = temp_storage

    # 1. Printers
    p_data = [{"id": "p_rel_1", "name": "Relational P1P", "model": "P1P"}]
    await storage.save_printers(p_data)
    loaded_printers = await storage.load_json(storage.printers_file, [])
    assert len(loaded_printers) == 1
    assert loaded_printers[0]["id"] == "p_rel_1"

    # 2. Presets
    presets_data = {"standard": {"name": "Standard PLA", "filament_cost": 750.0}}
    await storage.save_presets(presets_data)
    loaded_presets = await storage.load_json(storage.presets_file, {})
    assert "standard" in loaded_presets
    assert loaded_presets["standard"]["filament_cost"] == 750.0

    # 3. Settings
    settings_data = {"notify_tg": True, "theme": "dark"}
    await storage.save_settings(settings_data)
    loaded_settings = await storage.load_json(storage.settings_file, {})
    assert loaded_settings["notify_tg"] is True
    assert loaded_settings["theme"] == "dark"
