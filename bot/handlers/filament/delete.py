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
    warehouse_spools = {s_id: s for s_id, s in spools.items() if not s.get("assigned_printer_id")}
    if not warehouse_spools:
        await message.answer(
            "⚠️ На Складі немає вільних котушок для видалення (усі встановлені на принтери або склад порожній)."
            if u_lang != "en"
            else "⚠️ No free spools available to delete in warehouse (all mounted or stock is empty)."
        )
        return

    user["state"] = "select_spool_to_delete"
    await app.storage.save_user(user)
    await message.answer(
        "🗑️ <b>Оберіть котушку для видалення:</b>" if u_lang != "en" else "🗑️ <b>Select spool to delete:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(warehouse_spools, lang=u_lang),
    )
