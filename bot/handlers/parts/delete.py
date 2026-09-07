"""
Delete part handlers.
"""

from typing import Any
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.states import PartEditingStates

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["видалити", "🗑️ видалити", "delete", "🗑️ delete", "🗑️ видалити деталь", "видалити деталь"])
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(["видалити", "🗑️ видалити", "delete", "🗑️ delete", "🗑️ видалити деталь", "видалити деталь"])
)
async def handle_delete_part_start(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для видалення.")
        return

    if part_id and part_id in parts:
        del parts[part_id]
        await app.storage.save_json(app.storage.parts_file, parts)
        await message.answer("✅ <b>Деталь успішно видалено!</b>", parse_mode="HTML")
        from bot.handlers.parts.view import open_parts_list
        u_data = await app.storage.load_user(message.from_user.id)
        from utils.i18n import get_user_lang
        lang = get_user_lang(u_data)
        await open_parts_list(message, state, app, lang)
    else:
        from bot.keyboards import get_parts_inline_keyboard
        await state.set_state(PartEditingStates.select_part_for_delete)
        await message.answer("🗑️ <b>Оберіть деталь зі списку для видалення:</b>", parse_mode="HTML", reply_markup=get_parts_inline_keyboard(parts))

