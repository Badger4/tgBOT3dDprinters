"""
Delete part handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates

router = Router()


@router.message(PartEditingStates.in_parts_list, F.text.in_(["Видалити", "🗑️ Видалити", "Delete"]))
async def handle_delete_part_start(message: Message, state: FSMContext, app: Any) -> None:
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для видалення.")
        return
    await state.set_state(PartEditingStates.select_part_for_delete)
    await message.answer("Оберіть деталь для видалення.")
