"""
Printer print job control (pause, resume, stop) handlers.
"""

import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import get_printer_control_keyboard, get_printer_menu_keyboard

router = Router()


@router.message(
    F.text.lower().in_(
        [
            "🎛️ керування принтером",
            "керування принтером",
            "керування",
            "🎛️ printer control",
            "printer control",
            "control",
        ]
    )
)
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


@router.message(F.text.lower().in_(["🚫 пропустити об'єкт", "пропустити об'єкт", "🚫 skip object", "skip object"]))
async def handle_skip_objects_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        # Fallback to single active printer if only one is printing
        active_printers = [
            p for p in app.printers.values()
            if getattr(p, "is_online", True) and p.gcode_state in ["RUNNING", "PAUSE", "PREPARING", "PREPARATION", "BUILDING"]
        ]
        if len(active_printers) == 1:
            target_printer = active_printers[0]
        elif len(active_printers) > 1:
            await message.answer("⚠️ Декілька принтерів друкують одночасно. Спочатку відкрийте потрібний принтер у меню «🖨️ Принтери».")
            return
        else:
            await message.answer("⚠️ Наразі жоден принтер не друкує. Пропуск об'єктів доступний тільки під час активного друку.")
            return

    if target_printer.gcode_state not in ["RUNNING", "PAUSE", "PREPARING", "PREPARATION", "BUILDING"]:
        await message.answer(
            f"⚠️ Принтер <b>{html.escape(target_printer.name)}</b> зараз не друкує (стан: <code>{target_printer.gcode_state}</code>).\n"
            f"Пропуск об'єктів доступний тільки під час активного друку.",
            parse_mode=ParseMode.HTML,
        )
        return

    objects = target_printer.get_clean_job_objects()
    if not objects:
        if hasattr(target_printer, "_try_ftps_fetch"):
            target_printer._ftps_fetching = False
            target_printer._try_ftps_fetch()
            import asyncio

            await asyncio.sleep(1.0)
            objects = target_printer.get_clean_job_objects()

    if not objects:
        import json
        from config import STORAGE_DIR
        cache_file = STORAGE_DIR / "last_sliced_weight.json"
        if cache_file.exists():
            try:
                c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                if isinstance(c_data.get("objects"), list) and c_data["objects"]:
                    target_printer.current_job_objects = c_data["objects"]
                    objects = target_printer.current_job_objects
            except Exception:
                pass

    if not objects:
        await message.answer(
            f"ℹ️ Для поточного завдання друку на <b>{html.escape(target_printer.name)}</b> не виявлено списку об'єктів у .3mf файлі.\n\n"
            f"💡 <i>Об'єкти зчитуються автоматично з SD-карти принтера через FTPS або при завантаженні .3mf файлу через бот/веб-панель.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    logger.info(
        f"🚫 [Skip Menu] Rendering skip menu for [{target_printer.name}] with {len(objects)} objects: {[o.get('id') for o in objects]} (skipped: {getattr(target_printer, 'skipped_objects', [])})"
    )

    from aiogram.types import BufferedInputFile
    from bot.keyboards import build_skip_objects_keyboard
    from utils.image_utils import render_plate_diagram

    p_model = str(getattr(target_printer, "printer_model", "") or getattr(target_printer, "name", "")).lower()
    bed_size = (180, 180) if "mini" in p_model else (256, 256)
    # Hybrid approach: For <= 6 objects, send animated GIF highlighting each object ID; for > 6, send static diagram
    if len(objects) <= 6:
        gif_bytes = target_printer.get_plate_gif()
        if gif_bytes:
            try:
                await message.answer_animation(
                    animation=BufferedInputFile(gif_bytes, filename="plate_map.gif"),
                    caption=f"💡 <b>Анімована схема об'єктів ({html.escape(target_printer.name)}):</b>\n"
                    f"Кожен об'єкт по черзі підсвічується зеленим з номером <b>#ID</b>.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning(f"Could not send plate diagram animation for [{target_printer.name}]: {e}")
                gif_bytes = b""

        if not gif_bytes:
            diagram_bytes = render_plate_diagram(
                objects, bed_size_mm=bed_size, skipped_ids=getattr(target_printer, "skipped_objects", [])
            )
            if diagram_bytes:
                try:
                    await message.answer_photo(
                        photo=BufferedInputFile(diagram_bytes, filename="plate_map.jpg"),
                        caption=f"🗺️ <b>Схема розташування об'єктів ({html.escape(target_printer.name)}):</b>\n"
                        f"🟢 <i>Зелені — активні об'єкти</i> | 🔴 <i>Червоні — пропущені</i>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as e:
                    logger.warning(f"Could not send plate diagram photo for [{target_printer.name}]: {e}")
    else:
        diagram_bytes = render_plate_diagram(
            objects, bed_size_mm=bed_size, skipped_ids=getattr(target_printer, "skipped_objects", [])
        )
        if diagram_bytes:
            try:
                await message.answer_photo(
                    photo=BufferedInputFile(diagram_bytes, filename="plate_map.jpg"),
                    caption=f"🗺️ <b>Схема розташування об'єктів ({html.escape(target_printer.name)}):</b>\n"
                    f"🟢 <i>Зелені — активні об'єкти</i> | 🔴 <i>Червоні — пропущені</i>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning(f"Could not send plate diagram photo for [{target_printer.name}]: {e}")

    await message.answer(
        f"🚫 <b>Пропуск невдалого об'єкта</b> на <b>{html.escape(target_printer.name)}</b>:\n"
        f"Оберіть об'єкт на плейті, який потрібно припинити друкувати:",
        parse_mode=ParseMode.HTML,
        reply_markup=build_skip_objects_keyboard(target_printer),
    )


@router.message(F.text.lower().in_(["⏸️ пауза", "пауза", "⏸️ pause", "pause"]))
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


@router.message(F.text.lower().in_(["▶️ відновити друк", "відновити друк", "відновити", "продовжити", "▶️ resume", "resume", "▶️ resume print", "resume print"]))
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


@router.message(F.text.lower().in_(["⏹️ зупинити друк", "зупинити друк", "зупинити", "⏹️ stop print", "stop print", "⏹️ stop", "stop"]))
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


@router.message(F.text.lower().in_(["💡 підсвітка", "підсвітка", "💡 light", "light"]))
async def handle_toggle_light(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    if hasattr(target_printer, "toggle_chamber_light"):
        target_printer.toggle_chamber_light("toggle")
    elif hasattr(target_printer, "toggle_light"):
        target_printer.toggle_light()

    st_val = getattr(target_printer, "chamber_light_state", "off").upper()
    await message.answer(
        f"💡 Підсвітка для <b>{html.escape(target_printer.name)}</b>: <b>{st_val}</b>! 💡"
        if u_lang != "en"
        else f"💡 Light for <b>{html.escape(target_printer.name)}</b>: <b>{st_val}</b>! 💡",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
    )


@router.message(F.text.lower().in_(["⚡ швидкість", "швидкість", "⚡ speed", "speed"]))
async def handle_speed_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    spd_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🐢 Silent (50%)"), KeyboardButton(text="🚗 Standard (100%)")],
            [KeyboardButton(text="🏎️ Sport (124%)"), KeyboardButton(text="🚀 Ludicrous (166%)")],
            [KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")],
        ],
        resize_keyboard=True,
    )
    cur_mag = getattr(target_printer, "spd_mag", 100)
    await message.answer(
        f"⚡ <b>Оберіть режим швидкості для {html.escape(target_printer.name)}:</b>\nПоточна швидкість: <b>{cur_mag}%</b>"
        if u_lang != "en"
        else f"⚡ <b>Select speed mode for {html.escape(target_printer.name)}:</b>\nCurrent speed: <b>{cur_mag}%</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=spd_kb,
    )


@router.message(F.text.in_(["🐢 Silent (50%)", "🚗 Standard (100%)", "🏎️ Sport (124%)", "🚀 Ludicrous (166%)"]))
async def handle_set_speed(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    lvl_map = {"🐢 Silent (50%)": 1, "🚗 Standard (100%)": 2, "🏎️ Sport (124%)": 3, "🚀 Ludicrous (166%)": 4}
    lvl = lvl_map.get(message.text, 2)
    ok = target_printer.set_speed_level(lvl) if hasattr(target_printer, "set_speed_level") else target_printer.set_speed_profile(lvl)
    if ok:
        await message.answer(
            f"✅ Встановлено режим швидкості: <b>{html.escape(message.text)}</b> для {html.escape(target_printer.name)}! 🚀"
            if u_lang != "en"
            else f"✅ Speed mode set to: <b>{html.escape(message.text)}</b> for {html.escape(target_printer.name)}! 🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
        )
    else:
        await message.answer("⚠️ Не вдалося змінити швидкість (MQTT не підключено).")


@router.message(F.text.lower().in_(["🧹 скинути лічильник то", "скинути лічильник то", "провести то", "🧹 reset maintenance", "reset maintenance"]))
async def handle_reset_maintenance(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    if hasattr(target_printer, "reset_maintenance_counter"):
        target_printer.reset_maintenance_counter()
    elif hasattr(target_printer, "reset_maintenance"):
        target_printer.reset_maintenance("all")
    await app.save_printers_config()

    u_lang = user.get("language", "uk")
    interval = getattr(target_printer, "maintenance_interval_hours", 150.0)
    await message.answer(
        f"🧹 <b>Лічильник ТО для {html.escape(target_printer.name)} успішно скинуто!</b>\n"
        f"⏱️ Новий відлік до наступного ТО: <b>{interval} год</b>."
        if u_lang != "en"
        else f"🧹 <b>Maintenance counter for {html.escape(target_printer.name)} reset successfully!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
    )


# ==========================================
# Load / Unload Filament (from Printer Control menu)
# ==========================================

@router.message(F.text.lower().in_(["⬇️ завантажити філамент", "завантажити філамент", "⬇️ load filament", "load filament"]))
async def handle_load_filament_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    if getattr(target_printer, "is_printing", False) or target_printer.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
        await message.answer(
            "⚠️ <b>Неможливо завантажити: принтер зараз виконує друк!</b>" if not is_en
            else "⚠️ <b>Cannot load: printer is currently printing!</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    has_ams = bool(getattr(target_printer, "has_ams", False))
    pid = target_printer.id

    if has_ams:
        slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT (Зовнішній)"}
        buttons = []
        row = []
        for slot_k, slot_label in slot_names.items():
            row.append(InlineKeyboardButton(text=f"⬇️ {slot_label}", callback_data=f"hw_load:{pid}:{slot_k}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="✖️ Скасувати" if not is_en else "✖️ Cancel", callback_data="hw_skip")])
        await message.answer(
            f"⬇️ <b>{'Завантажити філамент' if not is_en else 'Load Filament'} — {html.escape(target_printer.name)}</b>\n"
            f"{'Оберіть слот AMS для завантаження:' if not is_en else 'Select AMS slot to load:'}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    else:
        # No AMS — load directly on VT slot 254
        try:
            success = target_printer.load_filament(slot_id="254")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error executing load_filament on [{target_printer.name}]: {e}")
            success = False

        if success:
            await message.answer(
                f"🔄 <b>Принтер {html.escape(target_printer.name)}: команду Load Filament надіслано!</b>\n"
                f"Принтер нагріє сопло та розпочне подачу нитки." if not is_en
                else f"🔄 <b>Printer {html.escape(target_printer.name)}: Load Filament command sent!</b>\n"
                f"The printer will heat the nozzle and start feeding filament.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
            )
        else:
            await message.answer(
                "❌ Помилка відправки команди (перевірте зв'язок з принтером)!" if not is_en
                else "❌ Failed to send command (check printer connection)!"
            )


@router.message(F.text.lower().in_(["⬆️ зняти філамент", "зняти філамент", "⬆️ unload filament", "unload filament"]))
async def handle_unload_filament_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None
    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    if getattr(target_printer, "is_printing", False) or target_printer.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
        await message.answer(
            "⚠️ <b>Неможливо зняти: принтер зараз виконує друк!</b>" if not is_en
            else "⚠️ <b>Cannot unload: printer is currently printing!</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    has_ams = bool(getattr(target_printer, "has_ams", False))
    pid = target_printer.id

    if has_ams:
        slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT (Зовнішній)"}
        buttons = []
        row = []
        for slot_k, slot_label in slot_names.items():
            row.append(InlineKeyboardButton(text=f"⬆️ {slot_label}", callback_data=f"hw_unload:{pid}:{slot_k}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="✖️ Скасувати" if not is_en else "✖️ Cancel", callback_data="hw_skip")])
        await message.answer(
            f"⬆️ <b>{'Зняти філамент' if not is_en else 'Unload Filament'} — {html.escape(target_printer.name)}</b>\n"
            f"{'Оберіть слот AMS для вивантаження:' if not is_en else 'Select AMS slot to unload:'}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    else:
        # No AMS — unload directly on VT slot 254
        try:
            success = target_printer.unload_filament(slot_id="254")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error executing unload_filament on [{target_printer.name}]: {e}")
            success = False

        if success:
            await message.answer(
                f"🔄 <b>Принтер {html.escape(target_printer.name)}: команду Unload Filament надіслано!</b>\n"
                f"Принтер обріже нитку та почне вивантаження." if not is_en
                else f"🔄 <b>Printer {html.escape(target_printer.name)}: Unload Filament command sent!</b>\n"
                f"The printer will cut and retract the filament.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
            )
        else:
            await message.answer(
                "❌ Помилка відправки команди (перевірте зв'язок з принтером)!" if not is_en
                else "❌ Failed to send command (check printer connection)!"
            )


