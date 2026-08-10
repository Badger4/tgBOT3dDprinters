"""
Printer management, telemetry, camera, GIF, settings, wizard, and deletion handlers.
"""
import html
import asyncio
import uuid
from aiogram import Router, types, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

from bot.keyboards import (
    get_printers_keyboard,
    get_printer_menu_keyboard,
    get_printer_control_keyboard,
)
from services.camera_stream import capture_real_camera_photo
from services.gif_generator import generate_printer_status_gif
from models.printer import BambuPrinter

router = Router()

@router.message(F.text.lower().in_(["🖨️ принтери", "принтери", "🖨️ назад до принтерів", "назад до принтерів"]))
async def handle_list_printers(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    await message.answer(
        "🖨️ <b>Ось твої принтери, Бака!</b>\nОбирай якийсь один і не дратуй мене даремно! 😤💅",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printers_keyboard(app.printers)
    )

@router.message(F.text.lower().in_(["📊 статус", "статус"]))
async def handle_printer_status(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    state_emoji = "🖨️" if target_printer.gcode_state == "RUNNING" else ("⏸️" if target_printer.gcode_state == "PAUSE" else ("🎉" if target_printer.gcode_state == "FINISH" else "💤"))
    status_txt = (
        f"<b>📊 Стан принтера: {target_printer.name}</b>\n"
        f"Х-хмпф! Тримай свою телеметрію... Тільки не думай, що я роблю це раді тебе! 😤\n\n"
        f"{state_emoji} <b>Стан:</b> <code>{target_printer.gcode_state}</code>\n"
        f"🔥 <b>Сопло:</b> <code>{target_printer.nozzle_temper}°C</code> | 🛏️ <b>Стіл:</b> <code>{target_printer.bed_temper}°C</code>\n"
        f"🧵 <b>Тип пластику:</b> <b>{target_printer.filament_type}</b>\n"
        f"📦 <b>Залишок на бабіні:</b> <b>{target_printer.filament_grams}g</b>\n"
    )
    if target_printer.gcode_state in ["RUNNING", "PAUSE"]:
        model_w = target_printer._current_job_grams or getattr(target_printer, "last_job_grams", 0.0)
        weight_str = f"<b>{model_w}g</b>" if model_w > 0 else "<b>Невизначено</b>"
        status_txt += (
            f"\n-----------------------------------\n"
            f"📄 <b>Модель:</b> <code>{target_printer.subtask_name or 'Невідомо'}</code>\n"
            f"⚖️ <b>Вага моделі:</b> {weight_str}\n"
            f"⏳ <b>Прогрес:</b> <b>{target_printer.mc_percent}%</b>\n"
            f"🧱 <b>Шар:</b> <b>{target_printer.layer_num} / {target_printer.total_layer_num}</b>\n"
            f"⏱️ <b>Залишилось часу:</b> ~<b>{target_printer.mc_remaining_time} хв</b>\n"
        )
        if model_w > 0:
            cost_info = target_printer.calculate_job_cost(model_w, target_printer.mc_remaining_time)
            status_txt += f"💰 <b>Собівартість:</b> <code>{cost_info['total_cost']} грн</code> <i>(пластик: {cost_info['filament_cost']}грн, світло: {cost_info['electricity_cost']}грн)</i>\n"
            spool_before = round(target_printer.filament_grams + (model_w if target_printer._job_deducted else 0.0), 2)
            if model_w > spool_before:
                deficit = round(model_w - spool_before, 2)
                status_txt += (
                    f"\n⚠️ <b>УВАГА! Недостатньо пластику!</b>\n"
                    f"❌ Вага моделі (<b>{model_w}g</b>) перевищує залишок (<b>{spool_before}g</b>).\n"
                    f"🚨 Не вистачає ~<b>{deficit}g</b>!\n"
                )
    maint_rem = max(0.0, target_printer.maintenance_interval_hours - target_printer.maintenance_hours_counter)
    status_txt += (
        f"⏱️ <b>Напрацювання:</b> <b>{target_printer.total_print_hours:.1f}г</b> (до ТО: <b>{maint_rem:.1f}г</b>)\n"
    )
    if getattr(target_printer, "last_job_grams", 0.0) > 0 and target_printer.gcode_state not in ["RUNNING", "PAUSE"]:
        status_txt += f"⚖️ <b>Остання вага моделі:</b> <b>{target_printer.last_job_grams}g</b>\n"

    status_txt += (
        f"\n-----------------------------------\n"
        f"🌐 <b>IP:</b> <tg-spoiler>{target_printer.ip}</tg-spoiler>\n"
        f"🔑 <b>Access Code:</b> <tg-spoiler>{target_printer.access_code}</tg-spoiler>\n"
        f"🔢 <b>SN:</b> <tg-spoiler>{target_printer.serial_number}</tg-spoiler>"
    )
    await message.answer(status_txt, parse_mode=ParseMode.HTML)

@router.message(F.text.lower().in_(["🧹 скинути лічильник то", "скинути лічильник то", "провести то"]))
async def handle_reset_maintenance(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.reset_maintenance_counter()
    await app.save_printers_config()
    await message.answer(
        f"🧹 <b>Лічильник ТО для {html.escape(target_printer.name)} успішно скинуто!</b>\n"
        f"⏱️ Новий відлік до наступного ТО: <b>{target_printer.maintenance_interval_hours} год</b>.\n"
        f"Дякую, що дбаєш про принтер, Бака! 🧼✨",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_menu_keyboard(target_printer)
    )

@router.message(F.text.lower().in_(["📷 камера", "📷 реальне фото (камера)", "фото", "камера"]))
async def handle_printer_camera(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    msg_wait = await message.answer("📷 ⏳ Отримую кадр з камери... Зачекай хвилинку, Бака!")
    photo_bytes = await capture_real_camera_photo(target_printer.ip, target_printer.access_code)
    if photo_bytes:
        photo_file = types.BufferedInputFile(photo_bytes, filename="real_camera.jpg")
        await message.answer_photo(
            photo=photo_file,
            caption=f"📷 *Жива камера: {target_printer.name}*\nХмпф! На, дивись на свій принтер! 📊 Стан: `{target_printer.gcode_state}` | ⏳ {target_printer.mc_percent}%",
            parse_mode=ParseMode.MARKDOWN
        )
        await msg_wait.delete()
    else:
        await message.answer(
            f"⚠️ *Порт камери недоступний для {target_printer.name}*\n"
            f"Х-хмпф! Перевірте Access Code або закрийте Bambu Handy, Бака!",
            parse_mode=ParseMode.MARKDOWN
        )
        await msg_wait.delete()

@router.message(F.text.lower().in_(["💡 підсвітка", "підсвітка"]))
async def handle_toggle_light(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.toggle_chamber_light("toggle")
    await message.answer(
        f"💡 Підсвітка для <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.chamber_light_state.upper()}</b>! І навіщо тобі це світло... Все одно нічого не бачиш, Бака! 🙄💡",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_menu_keyboard(target_printer)
    )

@router.message(F.text.lower().in_(["⚡ швидкість", "швидкість"]))
async def handle_speed_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    spd_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🐢 Silent (50%)"), KeyboardButton(text="🚗 Standard (100%)")],
        [KeyboardButton(text="🏎️ Sport (124%)"), KeyboardButton(text="🚀 Ludicrous (166%)")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)
    await message.answer(
        f"⚡ <b>Оберіть режим швидкості для {html.escape(target_printer.name)}:</b>\nХ-хмпф! Тільки не розжени принтер так, щоб він розвалився, Бака! 😤\nПоточна швидкість: <b>{target_printer.spd_mag}%</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=spd_kb
    )

@router.message(F.text.in_(["🐢 Silent (50%)", "🚗 Standard (100%)", "🏎️ Sport (124%)", "🚀 Ludicrous (166%)"]))
async def handle_set_speed(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    lvl_map = {"🐢 Silent (50%)": 1, "🚗 Standard (100%)": 2, "🏎️ Sport (124%)": 3, "🚀 Ludicrous (166%)": 4}
    lvl = lvl_map.get(message.text, 2)
    if target_printer.set_speed_level(lvl):
        await message.answer(
            f"✅ Встановлено режим швидкості: <b>{html.escape(message.text)}</b> для {html.escape(target_printer.name)}! І тільки спробуй щось зламати, Бака! 😤🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(target_printer)
        )
    else:
        await message.answer("⚠️ Не вдалося змінити швидкість (MQTT не підключено).")

@router.message(F.text.startswith("🔔 Сповіщення:") | F.text.startswith("🔕 Сповіщення:"))
async def handle_toggle_printer_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.notify = not target_printer.notify
    await app.save_printers_config()
    status_tsun = 'Увімкнено ✅ (тепер буду постійно на тебе бурчати!)' if target_printer.notify else 'Вимкнено 🔕 (нарешті відпочину від тебе!)'
    await message.answer(f"Сповіщення для {target_printer.name}: {status_tsun}", reply_markup=get_printer_menu_keyboard(target_printer))

@router.message(F.text.lower().in_(["🗑️ видалити принтер", "видалити принтер"]))
async def handle_delete_printer_request(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "confirm_delete_printer"
    await app.storage.save_user(user)
    await message.answer(
        f"⚠️ *ТИ ЩО, СУРЙОЗНО ХОЧЕШ ВИДАЛИТИ ПРИНТЕР {target_printer.name}?!*\nТи точно впевнений, чи знову кнопкою помилився, Бака?! 😤💥",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Так, видалити принтер")], [KeyboardButton(text="Ні, скасувати")]], resize_keyboard=True)
    )

@router.message(F.text == "➕ Додати принтер")
async def handle_add_printer_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_p_name"
    user["context_data"]["new_printer"] = {}
    await app.storage.save_user(user)
    await message.answer("Введіть *назву* нового принтера:", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Відміна")]], resize_keyboard=True))

@router.message(F.func(lambda m: m.text and (m.text.startswith("🖨️ ") or any(m.text.lower() == p.name.lower() for p in getattr(m, "_app_printers", {}).values()))))
async def handle_select_printer_by_name(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)

    matched_p = None
    text = message.text.strip()
    for p_id, printer in app.printers.items():
        if text == f"🖨️ {printer.name}" or text.lower() == printer.name.lower():
            matched_p = (p_id, printer)
            break

    if matched_p:
        p_id, printer = matched_p
        user["context_data"]["selected_printer_id"] = str(p_id)
        user["state"] = "printer_menu"
        await app.storage.save_user(user)
        await message.answer(
            f"<b>Керування принтером: {printer.name}</b>\n"
            f"Х-хмпф! Ось тобі меню для <b>{printer.name}</b>! Тільки дивись нічого не зламай, Бака! 😤💅\n\n"
            f"🌐 <b>IP:</b> <tg-spoiler>{printer.ip}</tg-spoiler>\n"
            f"🔑 <b>Access Code:</b> <tg-spoiler>{printer.access_code}</tg-spoiler>\n"
            f"🔢 <b>SN:</b> <tg-spoiler>{printer.serial_number}</tg-spoiler>\n\n"
            f"Залишок філаменту: <b>{printer.filament_grams}g</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(printer)
        )

PRINTER_STATES = {"add_p_name", "add_p_ip", "add_p_code", "add_p_sn", "confirm_delete_printer"}

async def printer_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    if state in PRINTER_STATES:
        return True
    text = message.text.strip()
    for printer in app.printers.values():
        if text == f"🖨️ {printer.name}" or text.lower() == printer.name.lower():
            return True
    return False

@router.message(printer_state_filter)
async def handle_printer_states(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    # Check printer selection first if text matches a printer
    for p_id, printer in app.printers.items():
        if text == f"🖨️ {printer.name}" or text.lower() == printer.name.lower():
            user["context_data"]["selected_printer_id"] = str(p_id)
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"<b>Керування принтером: {printer.name}</b>\n"
                f"Х-хмпф! Ось тобі меню для <b>{printer.name}</b>! Тільки дивись нічого не зламай, Бака! 😤💅\n\n"
                f"🌐 <b>IP:</b> <tg-spoiler>{printer.ip}</tg-spoiler>\n"
                f"🔑 <b>Access Code:</b> <tg-spoiler>{printer.access_code}</tg-spoiler>\n"
                f"🔢 <b>SN:</b> <tg-spoiler>{printer.serial_number}</tg-spoiler>\n\n"
                f"Залишок філаменту: <b>{printer.filament_grams}g</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_menu_keyboard(printer)
            )
            return True

    if state == "confirm_delete_printer" and target_printer:
        if text == "Так, видалити принтер":
            target_printer.destroy()
            del app.printers[target_printer.id]
            await app.save_printers_config()
            user["state"] = "idle"
            user["context_data"] = {}
            await app.storage.save_user(user)
            await message.answer("🗑️ Принтер успішно видалено!", reply_markup=get_printers_keyboard(app.printers))
        else:
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer("Видалення скасовано.", reply_markup=get_printer_menu_keyboard(target_printer))
        return True

    if state == "add_p_name":
        user["context_data"]["new_printer"]["name"] = text
        user["state"] = "add_p_ip"
        await app.storage.save_user(user)
        await message.answer("Введіть *IP адресу* принтера (наприклад 192.168.1.50):", parse_mode=ParseMode.MARKDOWN)
        return True

    if state == "add_p_ip":
        user["context_data"]["new_printer"]["ip"] = text
        user["state"] = "add_p_code"
        await app.storage.save_user(user)
        await message.answer("Введіть *Access Code / Код доступу* принтера:", parse_mode=ParseMode.MARKDOWN)
        return True

    if state == "add_p_code":
        user["context_data"]["new_printer"]["accessCode"] = text
        user["state"] = "add_p_sn"
        await app.storage.save_user(user)
        await message.answer("Введіть *Серійний номер (SN)* принтера:", parse_mode=ParseMode.MARKDOWN)
        return True

    if state == "add_p_sn":
        new_p_data = user["context_data"].get("new_printer", {})
        new_p_data["serialNumber"] = text
        new_p_data["id"] = str(uuid.uuid4())
        new_p_data["filament_grams"] = 1000.0
        new_p_data["notify"] = True

        p_obj = BambuPrinter(new_p_data, app.storage, save_callback=app.save_printers_config)
        p_obj.init_mqtt()
        app.printers[p_obj.id] = p_obj
        await app.save_printers_config()

        user["state"] = "idle"
        user["context_data"] = {}
        await app.storage.save_user(user)
        await message.answer("✅ *Принтер успішно збережено!*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_printers_keyboard(app.printers))
        return True

    return False
