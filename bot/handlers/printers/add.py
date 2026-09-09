"""
Add printer wizard handlers.
"""

import asyncio
import html
import uuid
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_printer_models_keyboard, get_printers_keyboard, get_main_keyboard
from config import logger
from models.printer import BambuPrinter

router = Router()


@router.message(F.text.lower().in_(["➕ додати принтер", "додати принтер", "➕ add printer", "add printer"]))
async def handle_add_printer_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "add_p_name"
    user.setdefault("context_data", {})["new_printer"] = {}
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
    u_lang = user.get("language", "uk")

    cancel_keywords = {"відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад", "cancel", "/cancel"}
    if text.lower() in cancel_keywords:
        user["state"] = "idle"
        user.get("context_data", {}).pop("new_printer", None)
        await app.storage.save_user(user)
        cancel_msg = "Додавання принтера скасовано." if u_lang != "en" else "Printer addition cancelled."
        await message.answer(cancel_msg, reply_markup=get_printers_keyboard(app.printers, lang=u_lang))
        return True

    if state == "add_p_name":
        user.setdefault("context_data", {})["new_printer"] = {"name": text}
        user["state"] = "add_p_model"
        await app.storage.save_user(user)
        msg_txt = "Оберіть модель принтера:" if u_lang != "en" else "Select printer model:"
        await message.answer(msg_txt, reply_markup=get_printer_models_keyboard())
        return True

    if state == "add_p_model":
        clean_model = text.replace("🖨️ ", "").strip()
        user.setdefault("context_data", {}).setdefault("new_printer", {})["printer_model"] = clean_model
        user["state"] = "add_p_ip"
        await app.storage.save_user(user)
        msg_txt = "Введіть IP-адресу принтера:" if u_lang != "en" else "Enter printer IP address:"
        await message.answer(msg_txt)
        return True

    if state == "add_p_ip":
        user.setdefault("context_data", {}).setdefault("new_printer", {})["ip"] = text
        user["state"] = "add_p_code"
        await app.storage.save_user(user)
        msg_txt = "Введіть Access Code:" if u_lang != "en" else "Enter Access Code:"
        await message.answer(msg_txt)
        return True

    if state == "add_p_code":
        user.setdefault("context_data", {}).setdefault("new_printer", {})["access_code"] = text
        user["state"] = "add_p_sn"
        await app.storage.save_user(user)
        msg_txt = "Введіть Серійний Номер:" if u_lang != "en" else "Enter Serial Number:"
        await message.answer(msg_txt)
        return True

    if state == "add_p_sn":
        new_p = user.get("context_data", {}).get("new_printer", {})
        new_p["serial_number"] = text
        p_id = str(uuid.uuid4())

        p_config = {
            "id": p_id,
            "name": new_p.get("name", "Bambu Printer"),
            "ip": new_p.get("ip", ""),
            "accessCode": new_p.get("access_code", ""),
            "serialNumber": text,
            "printer_model": new_p.get("printer_model", "X1C"),
            "filament_grams": 1000.0,
            "notify": True,
        }

        try:
            p_obj = BambuPrinter(p_config, app.storage, save_callback=app.save_printers_config)
            running_loop = asyncio.get_running_loop()
            p_obj._main_loop = running_loop
            asyncio.create_task(asyncio.to_thread(p_obj.init_mqtt, running_loop))
            app.printers[p_id] = p_obj
            await app.save_printers_config()

            user["state"] = "idle"
            user.get("context_data", {}).pop("new_printer", None)
            await app.storage.save_user(user)

            msg_txt = (
                f"✅ Принтер <b>{html.escape(p_obj.name)}</b> успішно додано!"
                if u_lang != "en"
                else f"✅ Printer <b>{html.escape(p_obj.name)}</b> successfully added!"
            )
            await message.answer(
                msg_txt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
            )
        except Exception as e:
            logger.error(f"Error adding printer: {e}")
            app.printers.pop(p_id, None)
            user["state"] = "idle"
            user.get("context_data", {}).pop("new_printer", None)
            await app.storage.save_user(user)
            err_msg = (
                f"❌ Помилка при додаванні принтера: {e}"
                if u_lang != "en"
                else f"❌ Error adding printer: {e}"
            )
            await message.answer(
                err_msg,
                reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
            )
        return True

    return False

