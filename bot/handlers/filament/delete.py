"""
Delete spool handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_spools_keyboard

router = Router()


@router.message(F.text.lower().in_(["🗑️ видалити котушку", "видалити котушку", "🗑️ видалити", "видалити", "🗑️ delete spool", "delete spool", "🗑️ delete", "delete"]))
async def handle_delete_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На Складі немає котушок для видалення." if u_lang != "en" else "⚠️ No spools available to delete.")
        return

    user["state"] = "select_spool_to_delete"
    await app.storage.save_user(user)
    await message.answer(
        "🗑️ <b>Оберіть котушку для видалення:</b>" if u_lang != "en" else "🗑️ <b>Select spool to delete:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(spools, lang=u_lang),
    )
