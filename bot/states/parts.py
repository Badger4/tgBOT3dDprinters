"""
FSM States for 3D Parts Library and Printing workflows.
"""

from aiogram.fsm.state import State, StatesGroup


class PartCreatingStates(StatesGroup):
    name = State()
    image = State()
    count = State()
    three_mf = State()


class AddPartStates(StatesGroup):
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


class EditPartStates(StatesGroup):
    select_part = State()
    select_property = State()
    edit_value = State()


class DeletePartStates(StatesGroup):
    select_part = State()
    confirm = State()


class PrintPartStates(StatesGroup):
    select_part = State()
    select_printer = State()
