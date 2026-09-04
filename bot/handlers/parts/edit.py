"""
Edit part handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates
from functions.i18n import get_user_lang

router = Router()


@router.message(PartEditingStates.in_parts_list, F.text.in_(["Редагувати", "✏️ Редагувати", "Edit"]))
async def handle_edit_part_start(message: Message, state: FSMContext, app: Any) -> None:
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для редагування.")
        return
    await state.set_state(PartEditingStates.select_part_for_edit)
    await message.answer("Оберіть деталь для редагування з списку вище.")
