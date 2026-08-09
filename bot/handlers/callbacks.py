"""
Callback query handlers for inline button interactions.
"""
from aiogram import Router, types
from aiogram.enums import ParseMode

router = Router()

@router.callback_query()
async def handle_callback_query(callback: types.CallbackQuery, app):
    data = callback.data or ""
    if data.startswith("deduct_"):
        parts = data.split("_")
        if len(parts) >= 3:
            p_id = parts[1]
            try:
                grams = float(parts[2])
            except ValueError:
                grams = 0.0

            printer = app.printers.get(p_id)
            if printer and grams > 0:
                old_w = printer.filament_grams
                printer.filament_grams = round(printer.filament_grams - grams, 2)
                await app.save_printers_config()
                await callback.answer(f"✅ Списано {grams}g! Новий залишок: {printer.filament_grams}g", show_alert=True)
                try:
                    await callback.message.reply(
                        f"✅ **Списано {grams}g для {printer.name}!**\n📦 Старий залишок: *{old_w}g* ➔ Новий залишок: *{printer.filament_grams}g*",
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
                return

    elif data.startswith("notify_photo_"):
        p_id = data.replace("notify_photo_", "")
        printer = app.printers.get(p_id)
        if printer:
            await callback.answer("📷 Отримую фото...")
            from services.camera_stream import capture_real_camera_photo
            from aiogram.types import BufferedInputFile
            photo = await capture_real_camera_photo(printer.ip, printer.access_code)
            if photo:
                await callback.message.reply_photo(
                    BufferedInputFile(photo, filename=f"{printer.name}.jpg"),
                    caption=f"📷 **Кадр з {printer.name}**",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await callback.message.reply("⚠️ Не вдалося отримати фото з камери.")
            return

    elif data.startswith("notify_pause_"):
        p_id = data.replace("notify_pause_", "")
        printer = app.printers.get(p_id)
        if printer:
            printer.pause_print()
            await callback.answer(f"⏸️ Надіслано команду Пауза на {printer.name}!", show_alert=True)
            return

    elif data.startswith("notify_light_"):
        p_id = data.replace("notify_light_", "")
        printer = app.printers.get(p_id)
        if printer:
            new_state = "off" if printer.chamber_light_state == "on" else "on"
            printer.set_chamber_light(new_state)
            await callback.answer(f"💡 Підсвітка {printer.name}: {new_state.upper()}", show_alert=True)
            return

    elif data.startswith("notify_maint_reset_"):
        p_id = data.replace("notify_maint_reset_", "")
        printer = app.printers.get(p_id)
        if printer:
            printer.reset_maintenance_counter()
            await app.save_printers_config()
            await callback.answer(f"🧹 Лічильник ТО для {printer.name} скинуто!", show_alert=True)
            try:
                await callback.message.reply(
                    f"✅ **ТО для принтера {printer.name} успішно виконано!**\n"
                    f"🧹 Лічильник відпрацьованих годин скинуто на *0.0h*.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass
            return

    await callback.answer()
