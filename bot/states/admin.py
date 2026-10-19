"""
FSM States for Administrator workflows.
"""

from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    manage_user = State()
