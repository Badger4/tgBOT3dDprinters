"""
Printer print job control (pause, resume, stop) handlers.
"""

import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import get_printer_control_keyboard, get_printer_menu_keyboard

router = Router()


@router.message(F.text.lower().in_(["🎛️ керування принтером", "керування принтером", "керування"]))
async def handle_control_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    await message.answer(
        f"🎛️ <b>Панель керування {html.escape(target_printer.name)}</b>\n"
        f"Х-хмпф! Обирай команду керування... Тільки дивись нічого не зіпсуй, Бака! 😤💅",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_control_keyboard(target_printer),
    )


@router.message(F.text.lower().in_(["⏸️ пауза", "пауза"]))
async def handle_pause_print(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    if target_printer.pause():
        await message.answer(
            f"⏸️ **Поставила на паузу** принтер *{target_printer.name}*! Задоволений тепер, Бака?! 😤",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_printer_menu_keyboard(target_printer),
        )
    else:
        await message.answer("⚠️ Не вдалося відправити паузу (MQTT не підключено).")


@router.message(F.text.lower().in_(["▶️ відновити друк", "відновити друк", "відновити", "продовжити"]))
async def handle_resume_print(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    if target_printer.resume():
        await message.answer(
            f"▶️ **Відновила друк** на *{target_printer.name}*! І тільки спробуй знову зупинити, Бака! 😤",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_printer_menu_keyboard(target_printer),
        )
    else:
        await message.answer("⚠️ Не вдалося відправити команду відновлення (MQTT не підключено).")


@router.message(F.text.lower().in_(["⏹️ зупинити друк", "зупинити друк", "зупинити"]))
async def handle_stop_print_request(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "confirm_stop_print"
    await app.storage.save_user(user)
    stop_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Так, зупинити друк")], [KeyboardButton(text="Ні, скасувати")]],
        resize_keyboard=True,
    )
    await message.answer(
        f"⚠️ **Ви дійсно хочете ЗУПИНИТИ друк на {target_printer.name}?**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=stop_kb,
    )


async def control_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") == "confirm_stop_print"


@router.message(control_state_filter)
async def handle_control_states(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if state == "confirm_stop_print" and target_printer:
        text = message.text.strip() if message.text else ""
        if text == "Так, зупинити друк":
            if target_printer.stop_print():
                user["state"] = "printer_menu"
                await app.storage.save_user(user)
                await message.answer(
                    f"⏹️ **Друк скасовано (зупинено)** на *{target_printer.name}*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_printer_menu_keyboard(target_printer),
                )
            else:
                await message.answer("⚠️ Не вдалося відправити команду зупинки через MQTT.")
        else:
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer("Зупинку друку скасовано.", reply_markup=get_printer_menu_keyboard(target_printer))
        return True
    return False
