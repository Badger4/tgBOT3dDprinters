"""
Edit spool handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_ams_slots_keyboard, get_filament_menu_keyboard, get_spools_keyboard

router = Router()


@router.message(F.text.lower().in_(["✏️ редагувати котушку", "редагувати котушку", "✏️ редагувати", "редагувати", "✏️ edit spool", "edit spool", "✏️ edit", "edit"]))
async def handle_edit_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    warehouse_spools = {s_id: s for s_id, s in spools.items() if not s.get("assigned_printer_id")}
    if not warehouse_spools:
        await message.answer(
            "⚠️ На Складі немає вільних котушок для редагування (усі встановлені на принтери або склад порожній)."
            if u_lang != "en"
            else "⚠️ No free spools available to edit in warehouse (all mounted or stock is empty)."
        )
        return

    user["state"] = "select_spool_to_edit"
    await app.storage.save_user(user)
    await message.answer(
        "✏️ <b>Оберіть котушку для редагування:</b>" if u_lang != "en" else "✏️ <b>Select spool to edit:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(warehouse_spools, lang=u_lang),
    )


@router.message(
    F.text.lower().in_(
        [
            "⚖️ змінити залишок ваги",
            "змінити залишок ваги",
            "✏️ ручне введення ваги",
            "ручне введення ваги",
            "✏️ manual weight input",
            "manual weight input",
            "✏️ змінити вагу",
            "змінити вагу",
            "✏️ edit weight",
            "edit weight",
        ]
    )
)
async def handle_manual_weight_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer(
            "⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»."
            if u_lang != "en"
            else "⚠️ Please select a printer first in «🖨️ Printers»."
        )
        return

    if getattr(target_printer, "has_ams", False):
        user["state"] = "select_slot_for_weight"
        await app.storage.save_user(user)
        await message.answer(
            f"📍 <b>Оберіть слот AMS або зовнішній слот (VT) для зміни залишку ваги принтера {html.escape(target_printer.name)}:</b>"
            if u_lang != "en"
            else f"📍 <b>Select AMS slot or external slot (VT) to edit remaining weight for {html.escape(target_printer.name)}:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_ams_slots_keyboard(target_printer, lang=u_lang),
        )
        return

    user.setdefault("context_data", {})["edit_weight_slot_key"] = "254"
    user.setdefault("context_data", {})["edit_weight_slot_label"] = "VT"
    user["state"] = "edit_filament_weight"
    await app.storage.save_user(user)
    await message.answer(
        f"Поточний залишок для <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.filament_grams}g</b>\n\n"
        f"Введіть нову залишкову вагу філаменту в грамах (наприклад <code>850</code>):"
        if u_lang != "en"
        else f"Current remaining for <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.filament_grams}g</b>\n\n"
        f"Enter new filament remaining weight in grams (e.g. <code>850</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
            resize_keyboard=True,
        ),
    )


@router.message(F.text.lower().in_(["💰 ціна 1 кг (грн)", "ціна 1 кг (грн)", "💰 price 1 kg", "price 1 kg"]))
async def handle_manual_price_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "edit_filament_price"
    await app.storage.save_user(user)
    await message.answer(
        f"Введіть вартість 1 кг пластику у грн для <b>{html.escape(target_printer.name)}</b> (поточна: {getattr(target_printer, 'price_per_kg', 850.0)} грн):"
        if u_lang != "en"
        else f"Enter cost of 1 kg filament in UAH for <b>{html.escape(target_printer.name)}</b> (current: {getattr(target_printer, 'price_per_kg', 850.0)} UAH):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
            resize_keyboard=True,
        ),
    )

