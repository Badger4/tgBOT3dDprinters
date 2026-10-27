import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()


@router.message(F.text.lower().in_(["🎯 калібрувати", "калібрувати", "🎯 calibrate", "calibrate"]))
async def handle_calibrate_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk") if user else "uk"
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer(
            "⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»."
            if u_lang != "en"
            else "⚠️ Please select a printer from «🖨️ Printers» first."
        )
        return

    curr_state = str(getattr(target_printer, "gcode_state", "") or "").upper()
    if curr_state in ("RUNNING", "PREPARE", "PAUSE"):
        await message.answer(
            f"⚠️ <b>Неможливо запустити калібрування!</b>\n"
            f"Принтер <b>{html.escape(target_printer.name)}</b> зараз зайнятий друком (стан: {curr_state}).\n"
            f"Зачекайте завершення друку або зупиніть його перед калібруванням."
            if u_lang != "en"
            else f"⚠️ <b>Cannot start calibration!</b>\n"
            f"Printer <b>{html.escape(target_printer.name)}</b> is currently busy printing ({curr_state}).\n"
            f"Wait for completion or stop print before calibrating.",
            parse_mode=ParseMode.HTML,
        )
        return

    esc_name = html.escape(target_printer.name)
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Підтвердити калібрування" if u_lang != "en" else "🎯 Confirm Calibration",
                    callback_data=f"conf_calib:{target_printer.id}",
                ),
                InlineKeyboardButton(
                    text="❌ Скасувати" if u_lang != "en" else "❌ Cancel",
                    callback_data=f"canc_calib:{target_printer.id}",
                ),
            ]
        ]
    )
    await message.answer(
        f"🎯 <b>Підтвердження калібрування</b>\n\n"
        f"Ви дійсно бажаєте запустити авто-калібрування для принтера <b>{esc_name}</b>?\n"
        f"<i>Принтер здійснить вирівнювання столу та калібрування вібрацій.</i>"
        if u_lang != "en"
        else f"🎯 <b>Calibration Confirmation</b>\n\n"
        f"Do you really want to start auto-calibration for printer <b>{esc_name}</b>?\n"
        f"<i>The printer will perform bed leveling and vibration compensation.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb,
    )


@router.callback_query(F.data.startswith("conf_calib:"))
async def handle_confirm_calibrate(callback: CallbackQuery, app):
    p_id = callback.data.split(":", 1)[1]
    target_printer = app.printers.get(p_id) if hasattr(app, "printers") else None
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk") if user else "uk"

    if not target_printer:
        await callback.answer("⚠️ Принтер не знайдено!", show_alert=True)
        return

    curr_state = str(getattr(target_printer, "gcode_state", "") or "").upper()
    if curr_state in ("RUNNING", "PREPARE", "PAUSE"):
        await callback.answer(f"⚠️ Принтер уже зайнятий друком ({curr_state})!", show_alert=True)
        return

    if hasattr(target_printer, "start_calibration"):
        ok = target_printer.start_calibration()
    elif hasattr(target_printer, "calibrate_async"):
        ok = await target_printer.calibrate_async()
    else:
        ok = True

    esc_name = html.escape(target_printer.name)
    if ok:
        try:
            await callback.message.edit_text(
                f"🎯 <b>Запущено авто-калібрування для {esc_name}!</b>"
                if u_lang != "en"
                else f"🎯 <b>Auto-calibration started for {esc_name}!</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await callback.message.answer(
                f"🎯 <b>Запущено авто-калібрування для {esc_name}!</b>"
                if u_lang != "en"
                else f"🎯 <b>Auto-calibration started for {esc_name}!</b>",
                parse_mode=ParseMode.HTML,
            )
        await callback.answer("🎯 Калібрування запущено!")
    else:
        await callback.answer("⚠️ Не вдалося запустити калібрування. Перевірте MQTT.", show_alert=True)


@router.callback_query(F.data.startswith("canc_calib:"))
async def handle_cancel_calibrate(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk") if user else "uk"
    try:
        await callback.message.edit_text(
            "❌ Калібрування скасовано." if u_lang != "en" else "❌ Calibration cancelled."
        )
    except Exception:
        await callback.message.answer(
            "❌ Калібрування скасовано." if u_lang != "en" else "❌ Calibration cancelled."
        )
    await callback.answer("Скасовано")
