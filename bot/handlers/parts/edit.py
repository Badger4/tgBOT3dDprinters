"""
Edit part handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates
from utils.i18n import get_user_lang

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["редагувати", "✏️ редагувати", "edit", "✏️ edit", "✏️ редагувати деталь", "редагувати деталь"])
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(["редагувати", "✏️ редагувати", "edit", "✏️ edit", "✏️ редагувати деталь", "редагувати деталь"])
)
async def handle_edit_part_start(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для редагування.")
        return

    if part_id and part_id in parts:
        from bot.keyboards import construct_part_info_keyboard
        part = parts[part_id]
        ikb = construct_part_info_keyboard(part)
        await message.answer(f"✏️ <b>Редагування деталі «{part.get('name', 'Деталь')}»:</b>\nОберіть поле для зміни:", parse_mode="HTML", reply_markup=ikb)
    else:
        from bot.keyboards import get_parts_inline_keyboard
        await state.set_state(PartEditingStates.select_part_for_edit)
        await message.answer("Оберіть деталь для редагування з списку нижче:", reply_markup=get_parts_inline_keyboard(parts))

