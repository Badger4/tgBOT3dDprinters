"""
Common navigation, back/cancel logic, and fallback handlers.
"""

import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import (
    get_main_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
)

router = Router()


@router.message(
    F.text.lower().in_(
        ["відміна", "стоп", "відмінити", "скасувати", "назад", "⬅️ назад", "головне меню", "⬅️ головне меню"]
    )
)
async def handle_cancel_or_back(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    ctx_data = user.get("context_data", {})
    text = message.text.strip().lower()

    # Case 1: In Add Printer Wizard -> return to Printers List
    if state in ["add_p_name", "add_p_ip", "add_p_code", "add_p_sn"]:
        user["state"] = "idle"
        if "new_printer" in user.get("context_data", {}):
            del user["context_data"]["new_printer"]
        await app.storage.save_user(user)
        await message.answer(
            "Додавання принтера скасовано! Передумав вже?! 😤", reply_markup=get_printers_keyboard(app.printers)
        )
        return

    # Case 2: In a sub-action inside a selected printer -> return to Printer Menu
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if target_printer and (
        state in ["edit_filament_weight", "confirm_stop_print", "confirm_delete_printer"]
        or text in ["назад", "⬅️ назад"]
    ):
        user["state"] = "printer_menu"
        await app.storage.save_user(user)
        await message.answer(
            f"Повертаю у меню <b>{html.escape(target_printer.name)}</b>! І більше не плутай кнопки, Бака! 🙄",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(target_printer),
        )
        return

    # Case 3: In Printer Menu -> return to Printers List
    if state == "printer_menu":
        user["state"] = "idle"
        user["context_data"] = {}
        await app.storage.save_user(user)
        await message.answer("Повертаю до списку принтерів! 🙄", reply_markup=get_printers_keyboard(app.printers))
        return

    # Default: Return to Main Menu
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    is_adm = await app.is_user_admin(chat_id)
    await message.answer(
        "🤖 *Головне меню 3D Ферми*\nХ-хмпф! Повернулися в меню... Обирай, що тобі треба! 😤",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(is_adm),
    )


@router.message(
    F.text.lower().in_(
        ["головне меню", "⬅️ головне меню", "повернутись в меню", "назад в меню", "⬅️ назад в меню", "вихід", "меню"]
    )
)
async def handle_main_menu_nav(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    is_adm = await app.is_user_admin(chat_id)
    await message.answer(
        "🤖 *Головне меню 3D Ферми*\nХ-хмпф! Повернулися в меню, Бака! 😤",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(is_adm),
    )


@router.message(F.text)
async def handle_fallback_text(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Додати в команду")]], resize_keyboard=True)
        await message.answer("👋 Щоб отримати доступ, натисни кнопку нижче, Бака!", reply_markup=keyboard)
        return

    await message.answer("Скористайтесь кнопками меню для навігації.")
