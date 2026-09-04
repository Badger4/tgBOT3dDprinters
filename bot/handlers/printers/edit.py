"""
Edit printer settings handlers.
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message
from bot.keyboards import get_edit_printer_keyboard

router = Router()


@router.message(F.text.lower().in_(["⚙️ налаштування принтера", "налаштування принтера", "✏️ редагувати принтер", "редагувати принтер", "⚙️ printer settings", "printer settings", "✏️ edit printer", "edit printer"]))
async def handle_edit_printer_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer("⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери».")
        return

    user["state"] = "edit_printer_menu"
    await app.storage.save_user(user)

    await message.answer(
        f"⚙️ <b>Налаштування принтера: {target_printer.name}</b>\n\nОберіть параметр для редагування:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_edit_printer_keyboard(lang=u_lang),
    )


@router.message(F.text.lower().in_(["✏️ назва принтера", "назва принтера", "✏️ printer name", "printer name"]))
async def handle_edit_printer_name_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "edit_p_name"
    await app.storage.save_user(user)
    await message.answer("Введіть нову назву принтера:")


@router.message(F.text.lower().in_(["🌐 ip адреса", "ip адреса", "🌐 ip address", "ip address"]))
async def handle_edit_printer_ip_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "edit_p_ip"
    await app.storage.save_user(user)
    await message.answer("Введіть нову IP-адресу принтера:")


@router.message(F.text.lower().in_(["🔢 серійний номер", "серійний номер", "🔢 serial number", "serial number"]))
async def handle_edit_printer_sn_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "edit_p_sn"
    await app.storage.save_user(user)
    await message.answer("Введіть новий серійний номер принтера:")


@router.message(F.text.lower().in_(["🔑 access code", "access code"]))
async def handle_edit_printer_code_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "edit_p_code"
    await app.storage.save_user(user)
    await message.answer("Введіть новий Access Code:")


EDIT_PRINTER_STATES = {"edit_p_name", "edit_p_ip", "edit_p_sn", "edit_p_code"}


async def edit_printer_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") in EDIT_PRINTER_STATES


@router.message(edit_printer_state_filter)
async def handle_edit_printer_states(message: Message, app) -> bool:
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""

    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        user["state"] = "idle"
        await app.storage.save_user(user)
        await message.answer("⚠️ Принтер не обрано.")
        return True

    if state == "edit_p_name":
        target_printer.name = text
    elif state == "edit_p_ip":
        target_printer.ip = text
    elif state == "edit_p_sn":
        target_printer.serial_number = text
    elif state == "edit_p_code":
        target_printer.access_code = text

    await app.save_printers_config()

    user["state"] = "printer_menu"
    await app.storage.save_user(user)
    await message.answer(f"✅ Оновлено параметр принтера {target_printer.name}!")
    return True

