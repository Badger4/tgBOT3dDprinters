"""
Aiogram 3 FSM State definitions for Telegram Bot UI flows.
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


class AdminStates(StatesGroup):
    manage_user = State()


class SpoolManagementStates(StatesGroup):
    select_spool_to_edit = State()
    select_edit_field = State()
    edit_name = State()
    edit_grams = State()
    edit_price = State()
    select_spool_to_delete = State()
    confirm_delete_spool = State()


class PartCreatingStates(StatesGroup):
    name = State()
    image = State()
    count = State()
    three_mf = State()


class PartEditingStates(StatesGroup):
    in_parts_list = State()
    in_part_info = State()
    property_edit = State()
    select_part_for_print = State()
    select_part_for_edit = State()
    select_part_for_delete = State()
    search_query = State()


