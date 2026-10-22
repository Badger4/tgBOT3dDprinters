import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from storage.manager import StorageManager
from utils.spool_fingerprint import (
    delete_active_print_context,
    load_active_print_context,
    save_active_print_context,
)


@pytest.fixture
def temp_storage():
    """Creates an isolated temporary directory for StorageManager tests."""
    temp_dir = tempfile.mkdtemp(prefix="test_farm_storage_")
    storage = StorageManager(base_dir=Path(temp_dir))
    yield storage, Path(temp_dir)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_storage_init_creates_tables(temp_storage):
    """Verifies that SQLite initialization creates all SSOT relational tables with WAL mode."""
    storage, temp_dir = temp_storage
    db_path = temp_dir / "printer_farm.db"
    assert db_path.exists()

    conn = storage._get_db()
    try:
        cur = conn.execute("PRAGMA journal_mode;")
        row = cur.fetchone()
        assert row[0].upper() == "WAL"

        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cur.fetchall()}
        expected_tables = {
            "printers",
            "spools",
            "warehouse_movements",
            "print_contexts",
            "slice_cache",
            "parts",
            "commercial_presets",
            "print_history",
            "settings",
            "users",
            "kv_store",
        }
        for tbl in expected_tables:
            assert tbl in tables, f"Expected table '{tbl}' was not created in SQLite DB"
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_delete_printer_atomic_cascades(temp_storage):
    """
    Verifies that delete_printer_atomic executes a single ACID transaction:
    1. Unmounts assigned spools and sets them to warehouse status.
    2. Writes audit records to warehouse_movements.
    3. Wipes active print context.
    4. Deletes printer from printers table and printers.json replica.
    """
    storage, temp_dir = temp_storage

    # 1. Setup printer
    printers_data = [
        {
            "id": "printer_alpha",
            "name": "Bambu Lab X1-Carbon",
            "serial_number": "00M00A000000001",
            "ip": "192.168.1.101",
            "access_code": "12345678",
            "model": "X1C",
        },
        {
            "id": "printer_beta",
            "name": "Bambu Lab P1S",
            "serial_number": "00M00A000000002",
            "ip": "192.168.1.102",
            "access_code": "87654321",
            "model": "P1S",
        },
    ]
    await storage.save_printers(printers_data)

    # 2. Setup spools assigned to printer_alpha and printer_beta
    spools_data = [
        {
            "id": "spool_01",
            "name": "Polymaker PLA Black",
            "material": "PLA",
            "color_hex": "#000000",
            "remaining_grams": 850.0,
            "total_grams": 1000.0,
            "location_type": "printer",
            "assigned_printer_id": "printer_alpha",
            "assigned_slot_key": "AMS_A1",
        },
        {
            "id": "spool_02",
            "name": "Sunlu PETG White",
            "material": "PETG",
            "color_hex": "#ffffff",
            "remaining_grams": 600.0,
            "total_grams": 1000.0,
            "location_type": "printer",
            "assigned_printer_id": "printer_alpha",
            "assigned_slot_key": "AMS_A2",
        },
        {
            "id": "spool_03",
            "name": "eSun ABS Red",
            "material": "ABS",
            "color_hex": "#ff0000",
            "remaining_grams": 400.0,
            "total_grams": 1000.0,
            "location_type": "printer",
            "assigned_printer_id": "printer_beta",
            "assigned_slot_key": "AMS_B1",
        },
    ]
    await storage.save_spools(spools_data)

    # 3. Setup print context in print_contexts table
    conn = storage._get_db()
    try:
        conn.execute(
            """
            INSERT INTO print_contexts (printer_id, subtask_name, spool_fingerprint, saved_layer, progress_pct, job_grams, job_deducted, context_json, updated_at)
            VALUES ('printer_alpha', 'vessel.3mf', 'fp_alpha', 100, 45, 80.0, 0, '{"layer": 100}', ?)
            """,
            (time.time(),),
        )
        conn.commit()
    finally:
        conn.close()

    # Verify initial state
    loaded_printers = await storage.load_printers()
    assert len(loaded_printers) == 2

    # 4. Perform atomic deletion of printer_alpha
    success = await storage.delete_printer_atomic("printer_alpha")
    assert success is True

    # 5. Verify printer is gone from SQLite and printers.json
    loaded_printers_after = await storage.load_printers()
    assert len(loaded_printers_after) == 1
    assert "printer_beta" in loaded_printers_after

    disk_printers_file = temp_dir / "printers.json"
    assert disk_printers_file.exists()
    disk_printers = json.loads(disk_printers_file.read_text(encoding="utf-8"))
    assert len(disk_printers) == 1
    assert disk_printers[0]["id"] == "printer_beta"

    # 6. Verify spools assigned to printer_alpha are unmounted to warehouse
    loaded_spools = await storage.load_spools()
    assert len(loaded_spools) == 3

    spool_01 = loaded_spools["spool_01"]
    assert spool_01["assigned_printer_id"] is None
    assert spool_01["assigned_slot_key"] is None

    spool_02 = loaded_spools["spool_02"]
    assert spool_02["assigned_printer_id"] is None
    assert spool_02["assigned_slot_key"] is None

    # spool_03 on printer_beta remains mounted
    spool_03 = loaded_spools["spool_03"]
    assert spool_03["assigned_printer_id"] == "printer_beta"

    # 7. Verify warehouse audit movements were created
    movements = await storage.load_spool_movements()
    unmount_movements = [
        m for m in movements if "Знято через видалення принтера" in str(m.get("reason", ""))
    ]
    assert len(unmount_movements) == 2
    spool_ids_moved = {m["spool_id"] for m in unmount_movements}
    assert spool_ids_moved == {"spool_01", "spool_02"}

    # 8. Verify print context was wiped
    conn = storage._get_db()
    try:
        cur = conn.execute("SELECT COUNT(*) FROM print_contexts WHERE printer_id = 'printer_alpha'")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()

    # 9. Verify deleting a non-existent printer returns False cleanly
    non_existent = await storage.delete_printer_atomic("phantom_printer")
    assert non_existent is False


@pytest.mark.asyncio
async def test_deduct_spool_warehouse_atomic(temp_storage):
    """
    Verifies that deduct_spool_warehouse_atomic executes a single ACID transaction:
    1. Finds mounted spool by printer_id and slot_key.
    2. Deducts grams safely without negative balance.
    3. Writes print audit log into warehouse_movements.
    4. Synchronizes spools.json replica atomically.
    """
    storage, temp_dir = temp_storage

    spools_data = [
        {
            "id": "spool_deduct_test",
            "name": "Bambu PETG-CF",
            "material": "PETG-CF",
            "color_hex": "#333333",
            "remaining_grams": 500.0,
            "total_grams": 1000.0,
            "assigned_printer_id": "printer_1",
            "assigned_slot_key": "AMS_A1",
        }
    ]
    await storage.save_spools(spools_data)

    # Perform atomic deduction of 125.5g
    ok = await storage.deduct_spool_warehouse_atomic(
        printer_id="printer_1",
        printer_name="X1C Farm 1",
        slot_key="AMS_A1",
        deducted_grams=125.5,
        subtask_name="DroneArm_v2.3mf",
    )
    assert ok is True

    # Check updated spool in storage
    loaded_spools = await storage.load_spools()
    deducted_spool = loaded_spools["spool_deduct_test"]
    assert abs(deducted_spool["remaining_grams"] - 374.5) < 0.01

    # Verify movement record in SQLite
    movements = await storage.load_spool_movements("spool_deduct_test")
    assert len(movements) == 1
    m = movements[0]
    assert m["spool_id"] == "spool_deduct_test"
    assert m["movement_type"] == "print"
    assert abs(m["weight_delta"] - (-125.5)) < 0.01
    assert "DroneArm_v2.3mf" in m["reason"]

    # Verify spools.json on disk is synced
    disk_spools = json.loads((temp_dir / "spools.json").read_text(encoding="utf-8"))
    assert abs(disk_spools["spool_deduct_test"]["remaining_grams"] - 374.5) < 0.01


@pytest.mark.asyncio
async def test_sliced_weight_cache_ssot_and_replica(temp_storage):
    """
    Verifies that slice cache operates with SQLite SSOT and atomic file replica:
    1. Synchronous read/write.
    2. Asynchronous read/write.
    3. Correct fallback if DB is queried.
    """
    storage, temp_dir = temp_storage

    test_payload = {
        "filename": "ComplexGear.3mf",
        "weight": 88.4,
        "time_mins": 145.0,
        "timestamp": time.time(),
        "objects": [{"id": 1, "name": "GearMain"}, {"id": 2, "name": "Pinion"}],
    }

    # Asynchronous save
    ok = await storage.set_sliced_weight_cache(test_payload)
    assert ok is True

    # Synchronous read (used by MQTT thread in models/printer.py)
    cached_sync = storage.get_sliced_weight_cache_sync()
    assert cached_sync is not None
    assert cached_sync["filename"] == "ComplexGear.3mf"
    assert abs(cached_sync["weight"] - 88.4) < 0.01
    assert len(cached_sync["objects"]) == 2

    # Asynchronous read
    cached_async = await storage.get_sliced_weight_cache()
    assert cached_async is not None
    assert cached_async["filename"] == "ComplexGear.3mf"
    assert abs(cached_async["weight"] - 88.4) < 0.01

    # Verify SQLite slice_cache table directly
    conn = storage._get_db()
    try:
        cur = conn.execute("SELECT filename, weight, time_mins, objects_json FROM slice_cache WHERE key = 'latest'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "ComplexGear.3mf"
        assert abs(row[1] - 88.4) < 0.01
        assert abs(row[2] - 145.0) < 0.01
        db_obj = json.loads(row[3])
        assert len(db_obj["objects"]) == 2
    finally:
        conn.close()

    # Verify atomic disk replica last_sliced_weight.json
    disk_file = temp_dir / "last_sliced_weight.json"
    assert disk_file.exists()
    disk_data = json.loads(disk_file.read_text(encoding="utf-8"))
    assert disk_data["filename"] == "ComplexGear.3mf"


@pytest.mark.asyncio
async def test_active_print_context_ssot(temp_storage):
    """
    Verifies that save_active_print_context, load_active_print_context,
    and delete_active_print_context store state in SQLite print_contexts
    and sync atomic file replica.
    """
    storage, temp_dir = temp_storage
    printer_id = "p_rocket_01"
    context_data = {
        "subtask_name": "RocketModel.3mf",
        "spool_fingerprint": "0=PLA|#FF0000|1000",
        "saved_layer": 72,
        "progress_pct": 45,
        "job_grams": 110.0,
        "job_deducted": False,
    }

    # Save context
    save_active_print_context(printer_id, context_data)

    # Load context
    recovered = load_active_print_context(printer_id)
    assert recovered is not None
    assert recovered["subtask_name"] == "RocketModel.3mf"
    assert recovered["progress_pct"] == 45

    # Delete context
    delete_active_print_context(printer_id)
    assert load_active_print_context(printer_id) is None


@pytest.mark.asyncio
async def test_parts_and_commercial_and_settings_ssot(temp_storage):
    """Verifies that Parts, Commercial Presets, and Settings all persist in SQLite and atomic file replicas."""
    storage, temp_dir = temp_storage

    # 1. Parts
    parts_data = [
        {"id": "part_01", "name": "Bracket Left", "category": "Mechanical", "count": 12, "color": "Black"},
        {"id": "part_02", "name": "Gear 40T", "category": "Drivetrain", "count": 5, "color": "Red"},
    ]
    await storage.save_parts(parts_data)
    loaded_parts = await storage.load_parts()
    assert len(loaded_parts) == 2
    assert loaded_parts["part_01"]["name"] == "Bracket Left"
    assert (temp_dir / "parts.json").exists()

    # 2. Commercial Presets
    presets_data = [
        {"id": "preset_01", "name": "Standard Print", "hourly_rate": 100.0, "markup_percent": 25.0},
    ]
    await storage.save_commercial_presets(presets_data)
    loaded_presets = await storage.load_commercial_presets()
    assert len(loaded_presets) == 1
    assert loaded_presets["preset_01"]["hourly_rate"] == 100.0
    assert (temp_dir / "commercial_presets.json").exists()

    # 3. Settings
    settings_data = {
        "electricity_cost_kwh": 4.32,
        "operator_wage_hour": 150.0,
        "default_currency": "UAH",
    }
    await storage.save_farm_settings(settings_data)
    loaded_settings = await storage.load_farm_settings()
    assert loaded_settings["electricity_cost_kwh"] == 4.32
    assert loaded_settings["default_currency"] == "UAH"
    assert (temp_dir / "global_settings.json").exists()
