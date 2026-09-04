"""
Add printer wizard handlers.
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_printer_models_keyboard, get_printers_keyboard, get_main_keyboard

router = Router()


@router.message(F.text.lower().in_(["➕ додати принтер", "додати принтер", "➕ add printer", "add printer"]))
async def handle_add_printer_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "add_p_name"
    user["context_data"]["new_printer"] = {}
    await app.storage.save_user(user)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
        resize_keyboard=True,
    )
    await message.answer(
        "➕ <b>Додавання нового принтера</b>\n\nВведіть назву принтера (наприклад: <i>Bambu Lab A1 mini 2</i>):"
        if u_lang != "en"
        else "➕ <b>Add new printer</b>\n\nEnter printer name (e.g. <i>Bambu Lab A1 mini 2</i>):",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


PRINTER_STATES = {
    "add_p_name",
    "add_p_model",
    "add_p_ip",
    "add_p_code",
    "add_p_sn",
}


async def printer_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") in PRINTER_STATES


@router.message(printer_state_filter)
async def handle_printer_states(message: Message, app) -> bool:
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""

    cancel_keywords = {"відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад", "cancel", "/cancel"}
    if text.lower() in cancel_keywords:
        user["state"] = "idle"
        user.get("context_data", {}).pop("new_printer", None)
        await app.storage.save_user(user)
        await message.answer("Додавання принтера скасовано.", reply_markup=get_printers_keyboard(app.printers))
        return True

    if state == "add_p_name":
        user["context_data"]["new_printer"]["name"] = text
        user["state"] = "add_p_model"
        await app.storage.save_user(user)
        await message.answer("Оберіть модель принтера:", reply_markup=get_printer_models_keyboard())
        return True

    if state == "add_p_model":
        clean_model = text.replace("🖨️ ", "").strip()
        user["context_data"]["new_printer"]["printer_model"] = clean_model
        user["state"] = "add_p_ip"
        await app.storage.save_user(user)
        await message.answer("Введіть IP-адресу принтера:")
        return True

    if state == "add_p_ip":
        user["context_data"]["new_printer"]["ip"] = text
        user["state"] = "add_p_code"
        await app.storage.save_user(user)
        await message.answer("Введіть Access Code:")
        return True

    if state == "add_p_code":
        user["context_data"]["new_printer"]["access_code"] = text
        user["state"] = "add_p_sn"
        await app.storage.save_user(user)
        await message.answer("Введіть Серійний Номер:")
        return True

    if state == "add_p_sn":
        new_p = user["context_data"]["new_printer"]
        new_p["serial_number"] = text
        import uuid
        p_id = str(uuid.uuid4())
        new_p["id"] = p_id

        app.printers[p_id] = new_p
        await app.save_printers_config()

        user["state"] = "idle"
        user["context_data"].pop("new_printer", None)
        await app.storage.save_user(user)
        await message.answer(f"✅ Принтер <b>{new_p['name']}</b> успішно додано!", parse_mode=ParseMode.HTML, reply_markup=get_printers_keyboard(app.printers))
        return True

    return False
