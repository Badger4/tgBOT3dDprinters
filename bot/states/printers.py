"""
FSM States for Printer workflows.
"""

from aiogram.fsm.state import State, StatesGroup


class AddPrinterStates(StatesGroup):
    name = State()
    ip = State()
    access_code = State()
    serial_number = State()


class PrinterMenuStates(StatesGroup):
    confirm_stop_print = State()
    edit_filament_weight = State()
    confirm_delete_printer = State()
