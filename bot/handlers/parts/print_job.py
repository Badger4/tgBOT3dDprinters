"""
Send part to print job handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates

router = Router()


@router.message(PartEditingStates.in_parts_list, F.text.in_(["Друк", "🚀 Друк", "Print"]))
async def handle_print_part_start(message: Message, state: FSMContext, app: Any) -> None:
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для друку.")
        return
    await state.set_state(PartEditingStates.select_part_for_print)
    await message.answer("Оберіть деталь для відправки на друк.")
