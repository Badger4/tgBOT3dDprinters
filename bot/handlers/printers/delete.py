import asyncio
import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_printer_menu_keyboard, get_printers_keyboard

router = Router()


@router.message(F.text.lower().in_(["🗑️ видалити принтер", "видалити принтер", "🗑️ delete printer", "delete printer"]))
async def handle_delete_printer_request(message: Message, app):
    chat_id = str(message.chat.id)
    if hasattr(app, "is_user_admin") and callable(app.is_user_admin):
        is_adm = app.is_user_admin(chat_id)
        if asyncio.iscoroutine(is_adm) or asyncio.isfuture(is_adm):
            is_adm = await is_adm
        if not is_adm:
            user = await app.storage.load_user(chat_id)
            u_lang = user.get("language", "uk")
            await message.answer(
                "⛔ <b>У вас немає прав адміністратора для цієї дії!</b>" if u_lang != "en" else "⛔ <b>Admin privileges required!</b>",
                parse_mode=ParseMode.HTML,
            )
            return

    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "confirm_delete_printer"
    await app.storage.save_user(user)
    u_lang = user.get("language", "uk")
    esc_p_name = html.escape(target_printer.name)
    await message.answer(
        f"⚠️ <b>Ви дійсно бажаєте видалити принтер {esc_p_name}?</b>"
        if u_lang != "en"
        else f"⚠️ <b>Are you sure you want to delete printer {esc_p_name}?</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Так, видалити принтер" if u_lang != "en" else "Yes, delete printer")],
                [KeyboardButton(text="Ні, скасувати" if u_lang != "en" else "No, cancel")],
            ],
            resize_keyboard=True,
        ),
    )


async def delete_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") == "confirm_delete_printer"


@router.message(delete_state_filter)
async def handle_confirm_delete_printer(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    u_lang = user.get("language", "uk")
    text = message.text.strip().lower()

    if text in ["так, видалити принтер", "yes, delete printer"]:
        if target_printer:
            try:
                target_printer.destroy()
            except Exception:
                pass
            app.printers.pop(target_printer.id, None)
            await app.save_printers_config()

        user["state"] = "idle"
        user["context_data"] = {}
        await app.storage.save_user(user)
        await message.answer(
            "🗑️ Принтер успішно видалено!" if u_lang != "en" else "🗑️ Printer deleted successfully!",
            reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
        )
    else:
        user["state"] = "printer_menu"
        await app.storage.save_user(user)
        await message.answer(
            "Видалення скасовано." if u_lang != "en" else "Deletion cancelled.",
            reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang) if target_printer else get_printers_keyboard(app.printers, lang=u_lang),
        )
