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
                active_key = printer.get_active_slot_key()
                old_w = printer.get_slot_grams(active_key)
                new_w = max(0.0, round(old_w - grams, 2))
                printer.set_slot_grams(new_w, active_key)
                printer.last_job_grams = grams
                await app.save_printers_config()
                await callback.answer(
                    f"✅ Списано {grams}g зі слота {active_key}! Новий залишок: {new_w}g", show_alert=True
                )
                try:
                    await callback.message.reply(
                        f"✅ **Списано {grams}g для {printer.name}!**\n🧵 **Слот AMS:** `{active_key}`\n📦 Старий залишок: *{old_w}g* ➔ Новий залишок: *{new_w}g*",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass
                return

    elif data.startswith("notify_photo_"):
        p_id = data.replace("notify_photo_", "")
        printer = app.printers.get(p_id)
        if printer:
            await callback.answer("📷 Отримую фото...")
            from aiogram.types import BufferedInputFile

            from services.camera_stream import capture_real_camera_photo

            photo = await capture_real_camera_photo(printer.ip, printer.access_code)
            if photo:
                await callback.message.reply_photo(
                    BufferedInputFile(photo, filename=f"{printer.name}.jpg"),
                    caption=f"📷 **Кадр з {printer.name}**",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await callback.message.reply("⚠️ Не вдалося отримати фото з камери.")
            return

    elif data.startswith("notify_pause_"):
        p_id = data.replace("notify_pause_", "")
        printer = app.printers.get(p_id)
        if printer:
            printer.pause()
            await callback.answer(f"⏸️ Надіслано команду Пауза на {printer.name}!", show_alert=True)
            return

    elif data.startswith("notify_light_"):
        p_id = data.replace("notify_light_", "")
        printer = app.printers.get(p_id)
        if printer:
            new_state = "off" if printer.chamber_light_state == "on" else "on"
            printer.toggle_chamber_light(new_state)
            await callback.answer(f"💡 Підсвітка {printer.name}: {new_state.upper()}", show_alert=True)
            return

    elif data.startswith("notify_calibrate_") or data.startswith("calibrate_printer_"):
        p_id = data.replace("notify_calibrate_", "").replace("calibrate_printer_", "")
        printer = app.printers.get(p_id)
        if printer:
            if printer.gcode_state == "RUNNING":
                await callback.answer("⚠️ Неможливо калібрувати під час друку!", show_alert=True)
                return
            ok = printer.start_calibration()
            if ok:
                await callback.answer(f"🎯 Запущено калібрування на {printer.name}!", show_alert=True)
                try:
                    await callback.message.reply(
                        f"🎯 **Запущено автоматичне калібрування на {printer.name}!**\n"
                        f"⚙️ Принтер виконує вирівнювання столу та тест резонансів (G32).",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception:
                    pass
            else:
                await callback.answer("⚠️ Не вдалося відправити команду калібрування.", show_alert=True)
            return

    elif data.startswith("notify_maint_reset_"):
        parts = data.replace("notify_maint_reset_", "").split("_")
        p_id = parts[0]
        item_key = parts[1] if len(parts) > 1 else "rails"
        printer = app.printers.get(p_id)
        if printer:
            printer.reset_maintenance_counter(item_key)
            await app.save_printers_config()
            item_name = printer.maintenance_items.get(item_key, {}).get("name", "ТО")
            await callback.answer(f"🧹 {item_name} для {printer.name} виконано!", show_alert=True)
            try:
                await callback.message.reply(
                    f"✅ **ТО ({item_name}) для принтера {printer.name} виконано!**\n"
                    f"🧹 Лічильник годин скинуто на *0.0h*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
            return

    elif data.startswith("approve_user_"):
        if not await app.is_user_admin(str(callback.from_user.id)):
            await callback.answer("⛔ Тільки адміністратор може керувати доступами!", show_alert=True)
            return
        target_uid = data.replace("approve_user_", "")
        user = await app.storage.load_user(target_uid)
        user["is_approved"] = True
        await app.storage.save_user(user)
        await callback.answer("✅ Доступ надано!", show_alert=True)
        try:
            await callback.message.edit_text(
                callback.message.html_text + "\n\n✅ <b>Схвалено адміністратором!</b>", parse_mode=ParseMode.HTML
            )
            await app.bot.send_message(
                chat_id=target_uid,
                text="🎉 <b>Адміністратор надав вам доступ до 3D Ферми!</b>\nНатисніть /start для переходу до головного меню.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    elif data.startswith("reject_user_"):
        if not await app.is_user_admin(str(callback.from_user.id)):
            await callback.answer("⛔ Тільки адміністратор може керувати доступами!", show_alert=True)
            return
        target_uid = data.replace("reject_user_", "")
        user = await app.storage.load_user(target_uid)
        user["is_approved"] = False
        await app.storage.save_user(user)
        await callback.answer("❌ Заявку відхилено", show_alert=True)
        try:
            await callback.message.edit_text(
                callback.message.html_text + "\n\n❌ <b>Відхилено адміністратором.</b>", parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        return

    elif data.startswith("make_admin_"):
        if not await app.is_user_admin(str(callback.from_user.id)):
            await callback.answer("⛔ Тільки адміністратор може керувати доступами!", show_alert=True)
            return
        target_uid = data.replace("make_admin_", "")
        user = await app.storage.load_user(target_uid)
        user["is_approved"] = True
        if "admin" not in user:
            user["admin"] = {}
        user["admin"]["access_admin"] = True
        await app.storage.save_user(user)
        await callback.answer("👑 Призначено адміністратором!", show_alert=True)
        try:
            await callback.message.edit_text(
                callback.message.html_text + "\n\n👑 <b>Призначено Адміністратором!</b>", parse_mode=ParseMode.HTML
            )
            await app.bot.send_message(
                chat_id=target_uid,
                text="👑 <b>Вам надано права Адміністратора 3D Ферми!</b>\nНатисніть /start.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    elif data.startswith("delete_user_"):
        if not await app.is_user_admin(str(callback.from_user.id)):
            await callback.answer("⛔ Тільки адміністратор може керувати доступами!", show_alert=True)
            return
        target_uid = data.replace("delete_user_", "")
        from config import ADMIN_CHAT_ID

        if str(target_uid) == str(ADMIN_CHAT_ID):
            await callback.answer("⚠️ Неможливо видалити головного адміністратора!", show_alert=True)
            return
        ok = await app.storage.delete_user(target_uid)
        if ok:
            await callback.answer("🗑️ Користувача видалено з бази!", show_alert=True)
            try:
                await callback.message.edit_text(
                    callback.message.html_text + "\n\n🗑️ <b>Повністю видалено з бази даних.</b>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        else:
            await callback.answer("⚠️ Не вдалося видалити користувача.", show_alert=True)
        return

    await callback.answer()
