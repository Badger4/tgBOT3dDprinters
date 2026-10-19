"""
Unified SQLite-backed persistence manager with WAL mode, optimized for flash storage.
Composes domain repositories (users, printers, spools, parts, commercial presets, and settings).
"""

from __future__ import annotations

from pathlib import Path

from storage.base import BaseStorage
from storage.commercial import CommercialRepository
from storage.parts import PartRepository
from storage.printers import PrinterRepository
from storage.settings import SettingsRepository
from storage.spools import SpoolRepository
from storage.users import UserRepository


class StorageManager(
    UserRepository,
    PrinterRepository,
    SpoolRepository,
    PartRepository,
    CommercialRepository,
    SettingsRepository,
):
    """
    Unified storage manager combining all entity repositories under a single facade.
    Maintains 100% backward-compatibility for all existing service and handler calls.
    """

    def __init__(self, base_dir: Path):
        super().__init__(base_dir=base_dir)
