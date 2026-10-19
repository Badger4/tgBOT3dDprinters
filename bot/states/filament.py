"""
FSM States for Spool and Filament workflows.
"""

from aiogram.fsm.state import State, StatesGroup


class SpoolManagementStates(StatesGroup):
    select_spool_to_edit = State()
    select_edit_field = State()
    edit_name = State()
    edit_grams = State()
    edit_price = State()
    select_spool_to_delete = State()
    confirm_delete_spool = State()


class AddSpoolStates(StatesGroup):
    name = State()
    type = State()
    weight = State()
    price = State()
    color = State()


class EditSpoolStates(StatesGroup):
    select_spool = State()
    select_field = State()
    edit_grams = State()
    edit_price = State()


class DeleteSpoolStates(StatesGroup):
    select_spool = State()
    confirm = State()


class MountSpoolStates(StatesGroup):
    select_spool = State()
    select_printer = State()
    select_slot = State()
