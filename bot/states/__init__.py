"""
Aiogram 3 FSM State definitions for Telegram Bot UI flows.
Modular package re-exporting all state groups for 100% backwards compatibility.
"""

from bot.states.admin import AdminStates
from bot.states.filament import (
    AddSpoolStates,
    DeleteSpoolStates,
    EditSpoolStates,
    MountSpoolStates,
    SpoolManagementStates,
)
from bot.states.parts import (
    AddPartStates,
    DeletePartStates,
    EditPartStates,
    PartCreatingStates,
    PartEditingStates,
    PrintPartStates,
)
from bot.states.printers import AddPrinterStates, PrinterMenuStates

__all__ = [
    "AddPrinterStates",
    "PrinterMenuStates",
    "AdminStates",
    "SpoolManagementStates",
    "AddSpoolStates",
    "EditSpoolStates",
    "DeleteSpoolStates",
    "MountSpoolStates",
    "PartCreatingStates",
    "AddPartStates",
    "PartEditingStates",
    "EditPartStates",
    "DeletePartStates",
    "PrintPartStates",
]
