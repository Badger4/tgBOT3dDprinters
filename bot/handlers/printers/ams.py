import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message

router = Router()


@router.message(F.text.lower().in_(["🎯 калібрувати", "калібрувати", "🎯 calibrate", "calibrate"]))
async def handle_calibrate_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk") if user else "uk"
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer("⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»." if u_lang != "en" else "⚠️ Please select a printer from «🖨️ Printers» first.")
        return

    if hasattr(target_printer, "start_calibration"):
        ok = target_printer.start_calibration()
    elif hasattr(target_printer, "calibrate_async"):
        ok = await target_printer.calibrate_async()
    else:
        ok = True

    esc_name = html.escape(target_printer.name)
    if ok:
        await message.answer(
            f"🎯 <b>Запущено авто-калібрування для {esc_name}!</b>" if u_lang != "en" else f"🎯 <b>Auto-calibration started for {esc_name}!</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await message.answer(
            "⚠️ Не вдалося запустити калібрування. Перевірте зв'язок по MQTT." if u_lang != "en" else "⚠️ Failed to start calibration. Check MQTT connection.",
        )
