"""
Unit tests for extracted printer services:
- services.printer_accounting_service
- services.printer_file_job_service
Verifies SRP decomposition, warehouse deductions, history recording, and cache invalidation.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.printer_accounting_service import (
    deduct_spool_warehouse,
    record_print_history_entry,
)
from services.printer_file_job_service import (
    invalidate_plate_gif_cache,
    render_plate_gif_cached,
)


@pytest.mark.asyncio
async def test_deduct_spool_warehouse_success():
    storage = MagicMock()
    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = None
    lock_cm.__aexit__.return_value = None
    storage.transaction_lock.return_value = lock_cm

    storage.load_spools = AsyncMock(
        return_value={
            "spool_1": {
                "name": "PLA White",
                "assigned_printer_id": "printer_1",
                "assigned_slot_key": "0",
                "remaining_grams": 500.0,
            }
        }
    )
    storage.save_spools = AsyncMock()
    storage.record_spool_movement = AsyncMock()

    loop = asyncio.get_running_loop()
    deduct_spool_warehouse(
        storage=storage,
        printer_id="printer_1",
        printer_name="Bambu P1S",
        slot_key="0",
        deducted_grams=25.5,
        subtask_name="Vase.3mf",
        loop=loop,
    )

    # Let scheduled task run
    await asyncio.sleep(0.05)

    storage.save_spools.assert_awaited_once()
    saved = storage.save_spools.call_args[0][0]
    assert saved["spool_1"]["remaining_grams"] == 474.5

    storage.record_spool_movement.assert_awaited_once()
    m_args = storage.record_spool_movement.call_args[1]
    assert m_args["spool_id"] == "spool_1"
    assert m_args["weight_change_g"] == -25.5
    assert m_args["new_weight_g"] == 474.5
    assert "Vase.3mf" in m_args["reason"]


@pytest.mark.asyncio
async def test_deduct_spool_warehouse_external_slot():
    storage = MagicMock()
    lock_cm = AsyncMock()
    lock_cm.__aenter__.return_value = None
    lock_cm.__aexit__.return_value = None
    storage.transaction_lock.return_value = lock_cm

    storage.load_spools = AsyncMock(
        return_value={
            "spool_ext": {
                "name": "PETG Black",
                "assigned_printer_id": "p2",
                "assigned_slot_key": "254",
                "remaining_grams": 200.0,
            }
        }
    )
    storage.save_spools = AsyncMock()
    storage.record_spool_movement = AsyncMock()

    loop = asyncio.get_running_loop()
    # Deducting with slot_key="255" should match "254"
    deduct_spool_warehouse(
        storage=storage,
        printer_id="p2",
        printer_name="A1 Mini",
        slot_key="255",
        deducted_grams=10.0,
        subtask_name="Holder",
        loop=loop,
    )

    await asyncio.sleep(0.05)
    storage.save_spools.assert_awaited_once()
    saved = storage.save_spools.call_args[0][0]
    assert saved["spool_ext"]["remaining_grams"] == 190.0


@pytest.mark.asyncio
async def test_deduct_spool_warehouse_zero_ignored():
    storage = MagicMock()
    storage.transaction_lock = MagicMock()

    deduct_spool_warehouse(
        storage=storage,
        printer_id="p1",
        printer_name="P1S",
        slot_key="0",
        deducted_grams=0.0,
    )
    storage.transaction_lock.assert_not_called()


@pytest.mark.asyncio
async def test_record_print_history_entry_cleans_subtask():
    storage = MagicMock()
    storage.add_history_entry = AsyncMock()

    printer = MagicMock()
    printer.name = "P1S Lab"
    printer.id = "p1"
    printer.serial_number = "01P00A12345"
    printer._custom_job_name = "test_print_v2.gcode.3mf"
    printer.filament_type = "PLA"

    loop = asyncio.get_running_loop()
    record_print_history_entry(
        storage=storage,
        printer=printer,
        final_weight=35.42,
        note_text="Success",
        loop=loop,
    )

    await asyncio.sleep(0.05)
    storage.add_history_entry.assert_awaited_once()
    entry = storage.add_history_entry.call_args[0][0]
    assert entry["printer_name"] == "P1S Lab"
    assert entry["subtask_name"] == "test_print_v2"
    assert entry["weight_g"] == 35.4
    assert entry["filament_type"] == "PLA"
    assert entry["note"] == "Success"


def test_plate_gif_caching_and_invalidation():
    printer = MagicMock()
    printer._plate_gif_cache = None
    printer.printer_model = "Bambu Lab P1S"
    printer.get_clean_job_objects.return_value = [{"id": 1, "name": "Box", "bbox": [10, 10, 50, 50]}]
    printer.skipped_objects = []

    with patch("services.printer_file_job_service.render_plate_gif", return_value=b"GIF89a_DUMMY"):
        data = render_plate_gif_cached(printer)
        assert data == b"GIF89a_DUMMY"
        assert printer._plate_gif_cache == b"GIF89a_DUMMY"

        # Repeated call should return cached bytes without calling render_plate_gif again
        with patch("services.printer_file_job_service.render_plate_gif", side_effect=RuntimeError):
            assert render_plate_gif_cached(printer) == b"GIF89a_DUMMY"

        # Invalidate cache
        invalidate_plate_gif_cache(printer)
        assert printer._plate_gif_cache is None
