"""
Callback query handlers for inline button interactions.
"""

import html

from aiogram import Router, types
from config import logger
from aiogram.enums import ParseMode

router = Router()


@router.callback_query()
async def handle_callback_query(callback: types.CallbackQuery, app):
    data = callback.data or ""
    if data.startswith("deduct_"):
        tail = data.removeprefix("deduct_")
        if tail.startswith("w_"):
            tail = tail.removeprefix("w_")
        p_id = None
        grams = 0.0
        if "_" in tail:
            p_id, grams_str = tail.rsplit("_", 1)
            try:
                grams = float(grams_str)
            except ValueError:
                grams = 0.0
        else:
            p_id = tail

        printer = app.printers.get(p_id) if p_id else None
        if not printer and p_id:
            printer = next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)

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
                        f"✅ <b>Списано {grams}g для {html.escape(printer.name)}!</b>\n🧵 <b>Слот AMS:</b> <code>{html.escape(str(active_key))}</code>\n📦 Старий залишок: <i>{old_w}g</i> ➔ Новий залишок: <i>{new_w}g</i>",
                        parse_mode=ParseMode.HTML,
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
                    caption=f"📷 <b>Кадр з {html.escape(printer.name)}</b>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await callback.message.reply("⚠️ Не вдалося отримати фото з камери.")
            return

    elif data.startswith("notify_pause_"):
        p_id = data.replace("notify_pause_", "")
        printer = app.printers.get(p_id)
        if printer:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            confirm_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="⚠️ Підтвердити ПАУЗУ", callback_data=f"conf_notify_pause_{p_id}"),
                        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"canc_notify_pause_{p_id}"),
                    ]
                ]
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=confirm_kb)
            except Exception:
                pass
            await callback.answer("⚠️ Натисніть 'Підтвердити ПАУЗУ' для зупинки друку!")
            return

    elif data.startswith("conf_notify_pause_"):
        p_id = data.replace("conf_notify_pause_", "")
        printer = app.printers.get(p_id)
        if printer:
            printer.pause()
            from bot.keyboards.notifications import get_error_notification_inline_keyboard
            try:
                await callback.message.edit_reply_markup(reply_markup=get_error_notification_inline_keyboard(p_id))
            except Exception:
                pass
            await callback.answer(f"⏸️ Надіслано команду Пауза на {printer.name}!", show_alert=True)
            return

    elif data.startswith("canc_notify_pause_"):
        p_id = data.replace("canc_notify_pause_", "")
        from bot.keyboards.notifications import get_notification_inline_keyboard
        try:
            await callback.message.edit_reply_markup(reply_markup=get_notification_inline_keyboard(p_id))
        except Exception:
            pass
        await callback.answer("Паузу скасовано.")
        return

    elif data.startswith("notify_resume_"):
        p_id = data.replace("notify_resume_", "")
        printer = app.printers.get(p_id)
        if printer:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            confirm_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="▶️ Підтвердити ВІДНОВЛЕННЯ", callback_data=f"conf_notify_resume_{p_id}"),
                        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"canc_notify_resume_{p_id}"),
                    ]
                ]
            )
            try:
                await callback.message.edit_reply_markup(reply_markup=confirm_kb)
            except Exception:
                pass
            await callback.answer("▶️ Натисніть 'Підтвердити ВІДНОВЛЕННЯ'!")
            return

    elif data.startswith("conf_notify_resume_"):
        p_id = data.replace("conf_notify_resume_", "")
        printer = app.printers.get(p_id)
        if printer:
            res = printer.resume()
            from bot.keyboards.notifications import get_notification_inline_keyboard
            try:
                await callback.message.edit_reply_markup(reply_markup=get_notification_inline_keyboard(p_id))
            except Exception:
                pass
            if res:
                await callback.answer(f"▶️ Надіслано команду Відновити на {printer.name}!", show_alert=True)
            else:
                await callback.answer("⚠️ Не вдалося відновити (MQTT не підключено).", show_alert=True)
            return

    elif data.startswith("canc_notify_resume_"):
        p_id = data.replace("canc_notify_resume_", "")
        from bot.keyboards.notifications import get_error_notification_inline_keyboard
        try:
            await callback.message.edit_reply_markup(reply_markup=get_error_notification_inline_keyboard(p_id))
        except Exception:
            pass
        await callback.answer("Відновлення скасовано.")
        return

    elif data.startswith("notify_light_"):
        p_id = data.replace("notify_light_", "")
        printer = app.printers.get(p_id)
        if printer:
            new_state = "off" if printer.chamber_light_state == "on" else "on"
            printer.toggle_chamber_light(new_state)
            await callback.answer(f"💡 Підсвітка {printer.name}: {new_state.upper()}", show_alert=True)
            return

    elif data.startswith("clear_bed_"):
        p_id = data.replace("clear_bed_", "")
        printer = app.printers.get(p_id)
        if printer:
            printer.finish_timestamp = 0.0
            if hasattr(app, "save_printers_config"):
                await app.save_printers_config()
            await callback.answer(
                f"🧹 Стіл принтера {printer.name} позначено як очищений! Принтер готовий до роботи ✅",
                show_alert=True,
            )
            try:
                await callback.message.reply(
                    f"🧹 <b>Стіл принтера {html.escape(printer.name)} очищено!</b>\n"
                    f"✅ Принтер вільний та готовий до наступного друку.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
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
                        f"🎯 <b>Запущено автоматичне калібрування на {html.escape(printer.name)}!</b>\n"
                        f"⚙️ Принтер виконує вирівнювання столу та тест резонансів (G32).",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            else:
                await callback.answer("⚠️ Не вдалося відправити команду калібрування.", show_alert=True)
            return

    elif data.startswith("notify_maint_reset_") or data.startswith("nmr:"):
        if data.startswith("nmr:"):
            parts = data.replace("nmr:", "").split(":")
            p_id = parts[0]
            item_key = parts[1] if len(parts) > 1 else "rails"
            printer = app.printers.get(p_id) or next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)
        else:
            tail = data.removeprefix("notify_maint_reset_")
            printer = None
            item_key = "rails"
            for pid, p in app.printers.items():
                if tail.startswith(pid + "_"):
                    printer = p
                    item_key = tail[len(pid) + 1:]
                    break
                elif tail.startswith(pid[:12] + "_"):
                    printer = p
                    item_key = tail[len(pid[:12]) + 1:]
                    break
            if not printer:
                if "_" in tail:
                    p_id, item_key = tail.rsplit("_", 1)
                    printer = app.printers.get(p_id) or next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)
                else:
                    printer = app.printers.get(tail) or next((p for pid, p in app.printers.items() if pid.startswith(tail)), None)

        if printer:
            printer.reset_maintenance_counter(item_key)
            await app.save_printers_config()
            item_name = printer.maintenance_items.get(item_key, {}).get("name", "ТО")
            await callback.answer(f"🧹 {item_name} для {printer.name} виконано!", show_alert=True)
            try:
                await callback.message.reply(
                    f"✅ <b>ТО ({html.escape(item_name)}) для принтера {html.escape(printer.name)} виконано!</b>\n"
                    f"🧹 Лічильник годин скинуто на <b>0.0h</b>.",
                    parse_mode=ParseMode.HTML,
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
            from bot.keyboards import get_main_keyboard
            is_target_adm = await app.is_user_admin(target_uid)
            u_lang = user.get("language", "uk")
            await app.bot.send_message(
                chat_id=target_uid,
                text="🎉 <b>Адміністратор надав вам доступ до 3D Ферми!</b>\nГоловне меню активовано 🚀" if u_lang != "en" else "🎉 <b>Administrator granted you access to 3D Farm!</b>\nMain menu activated 🚀",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(is_target_adm, lang=u_lang),
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
            from bot.keyboards import get_main_keyboard
            u_lang = user.get("language", "uk")
            await app.bot.send_message(
                chat_id=target_uid,
                text="👑 <b>Вам надано права Адміністратора 3D Ферми!</b>\nГоловне меню активовано 🚀" if u_lang != "en" else "👑 <b>You have been granted Administrator rights to 3D Farm!</b>\nMain menu activated 🚀",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_keyboard(True, lang=u_lang),
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

    elif data.startswith(("skip_obj_act:", "skip_obj_cfm:", "skip_obj_back:", "skip_obj_ref:", "skip_obj_cls:", "skip_obj_stop:", "skip_obj_sel:", "skip_obj_done:")):
        if data.startswith("skip_obj_done:"):
            await callback.answer("ℹ️ Цей об'єкт вже пропущено на плейті!", show_alert=True)
            return

        chat_id = str(
            callback.from_user.id
            if callback.from_user
            else (callback.message.chat.id if callback.message else "")
        )
        user = await app.storage.load_user(chat_id) if (chat_id and hasattr(app, "storage")) else {}
        user = user or {}
        is_authorized = bool(user.get("is_approved", False) or user.get("is_admin", False) or user.get("role") == "admin")
        if not is_authorized and chat_id and hasattr(app, "is_user_admin"):
            try:
                is_authorized = bool(await app.is_user_admin(chat_id))
            except Exception:
                pass
        if not is_authorized:
            await callback.answer("⛔ Доступ заборонено: потрібні права оператора або адміністратора!", show_alert=True)
            return

        parts = data.split(":")
        cmd = parts[0]
        p_id = parts[1] if len(parts) > 1 else ""
        printer = app.printers.get(p_id)

        if cmd == "skip_obj_cls":
            await callback.answer("Закрито")
            if callback.message:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
            return

        if not printer:
            await callback.answer("⚠️ Принтер не знайдено", show_alert=True)
            return

        if cmd == "skip_obj_sel":
            await callback.answer(f"Обрано {printer.name}")
            ctx = user.get("context_data", {})
            ctx["selected_printer_id"] = printer.id
            user["context_data"] = ctx
            if hasattr(app, "storage"):
                await app.storage.save_user(user)
            if callback.message:
                from bot.handlers.control import render_skip_objects_menu_for_printer
                await render_skip_objects_menu_for_printer(callback.message, printer, app)
            return

        if cmd in ("skip_obj_back", "skip_obj_ref"):
            from bot.keyboards import build_skip_objects_keyboard
            await callback.answer("🔄 Оновлено" if cmd == "skip_obj_ref" else "↩️ Скасовано")
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(reply_markup=build_skip_objects_keyboard(printer))
                except Exception:
                    pass
            return

        if cmd == "skip_obj_stop":
            stop_fn = getattr(printer, "stop_print", getattr(printer, "stop", None))
            if callable(stop_fn) and stop_fn():
                await callback.answer("🛑 Друк зупинено!", show_alert=True)
                if callback.message:
                    await callback.message.answer(
                        f"🛑 <b>Друк на {html.escape(printer.name)} зупинено</b>, оскільки всі об'єкти на столі було пропущено.",
                        parse_mode=ParseMode.HTML,
                    )
            else:
                await callback.answer("⚠️ Не вдалося відправити команду зупинки", show_alert=True)
            return

        if cmd == "skip_obj_act" and len(parts) == 3:
            obj_id = parts[2]
            try:
                int(obj_id)
            except ValueError:
                await callback.answer("⚠️ Некоректний ID об'єкта", show_alert=True)
                return
            from bot.keyboards import build_skip_object_confirm_keyboard
            await callback.answer(f"⚠️ Підтвердіть пропуск об'єкта #{obj_id}")
            if callback.message:
                try:
                    await callback.message.edit_reply_markup(
                        reply_markup=build_skip_object_confirm_keyboard(printer, obj_id)
                    )
                except Exception as e:
                    logger.warning(f"Failed to show skip confirm keyboard: {e}")
            return

        if cmd == "skip_obj_cfm" and len(parts) == 3:
            obj_id = parts[2]
            try:
                int_id = int(obj_id)
            except ValueError:
                await callback.answer("⚠️ Некоректний ID об'єкта", show_alert=True)
                return

            ok, msg = await printer.skip_objects_async([int_id])
            if ok:
                await callback.answer(f"✅ Об'єкт #{obj_id} позначено на пропуск!", show_alert=True)
                try:
                    from bot.keyboards import build_skip_objects_keyboard
                    if callback.message:
                        await callback.message.edit_reply_markup(
                            reply_markup=build_skip_objects_keyboard(printer)
                        )
                        extra_warn = ""
                        if hasattr(printer, "is_all_objects_skipped") and printer.is_all_objects_skipped():
                            extra_warn = "\n⚠️ <b>Увага: всі об'єкти на столі пропущено!</b> Рекомендується зупинити друк кнопкою вище, щоб принтер не друкував у повітрі."
                        await callback.message.answer(
                            f"🚫 <b>Команду пропуску об'єкта #{obj_id} надіслано на принтер {html.escape(printer.name)}!</b>\n"
                            f"ℹ️ Принтер омине цей об'єкт на наступних шарах друку.{extra_warn}",
                            parse_mode=ParseMode.HTML,
                        )
                except Exception as e:
                    logger.warning(f"Failed to update skip objects message: {e}")
            else:
                await callback.answer(f"⚠️ {msg}", show_alert=True)
            return

    await callback.answer()
