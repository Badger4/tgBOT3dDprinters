"""
Delete part handlers.
"""

import html
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from bot.states import PartEditingStates
from utils.i18n import get_user_lang

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
        part = parts[part_id]
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🗑️ Підтвердити видалення", callback_data=f"conf_del_part:{part_id}"),
                    InlineKeyboardButton(text="❌ Скасувати", callback_data=f"canc_del_part:{part_id}"),
                ]
            ]
        )
        await message.answer(
            f"⚠️ <b>Ви підтверджуєте видалення деталі?</b>\n\n"
            f"🧩 Деталь: <b>{html.escape(part.get('name', 'Деталь'))}</b>\n"
            f"<i>Цю дію неможливо скасувати!</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_kb,
        )
    else:
        from bot.keyboards import get_parts_inline_keyboard
        await state.set_state(PartEditingStates.select_part_for_delete)
        await message.answer("🗑️ <b>Оберіть деталь зі списку для видалення:</b>", parse_mode=ParseMode.HTML, reply_markup=get_parts_inline_keyboard(parts))


@router.callback_query(F.data.startswith("conf_del_part:"))
async def handle_confirm_delete_part(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    part_id = callback.data.split(":", 1)[1]
    parts = await app.storage.load_parts()
    if part_id in parts:
        deleted_name = parts[part_id].get("name", "Деталь")
        del parts[part_id]
        await app.storage.save_parts(parts)
        await callback.message.edit_text(
            f"✅ <b>Деталь «{html.escape(deleted_name)}» успішно видалено!</b>", parse_mode=ParseMode.HTML
        )
        from bot.handlers.parts.view import open_parts_list
        u_data = await app.storage.load_user(callback.from_user.id)
        lang = get_user_lang(u_data)
        await open_parts_list(callback.message, state, app, lang)
    else:
        await callback.answer("⚠️ Деталь вже видалено!", show_alert=True)
    await callback.answer("Видалено")


@router.callback_query(F.data.startswith("canc_del_part:"))
async def handle_cancel_delete_part(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    await callback.message.edit_text("❌ Видалення деталі скасовано.")
    from bot.handlers.parts.view import open_parts_list
    u_data = await app.storage.load_user(callback.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(callback.message, state, app, lang)
    await callback.answer("Скасовано")
