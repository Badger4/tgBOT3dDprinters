"""
Printer management, telemetry, camera, GIF, settings, wizard, and deletion handlers.
"""

import asyncio
import html
import uuid

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import (
    get_printer_control_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
)
from models.printer import BambuPrinter
from services.camera_stream import capture_real_camera_photo

router = Router()


@router.message(F.text.lower().in_(["🖨️ принтери", "принтери", "🖨️ назад до принтерів", "назад до принтерів", "🖨️ printers", "printers", "🖨️ back to printers", "back to printers"]))
async def handle_list_printers(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    u_lang = user.get("language", "uk")
    await message.answer(
        "🖨️ <b>Ось твої принтери, Бака!</b>\nОбирай якийсь один і не дратуй мене даремно! 😤💅" if u_lang != "en" else "🖨️ <b>Here are your printers!</b>\nSelect one to view controls and status! 🚀",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
    )


@router.message(F.text.lower().in_(["📊 статус", "статус", "📊 status", "status"]))
async def handle_printer_status(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    state_emoji = (
        "🖨️"
        if target_printer.gcode_state == "RUNNING"
        else (
            "⏸️" if target_printer.gcode_state == "PAUSE" else ("🎉" if target_printer.gcode_state == "FINISH" else "💤")
        )
    )
    nozzle_target = getattr(target_printer, "nozzle_target_temper", 0)
    bed_target = getattr(target_printer, "bed_target_temper", 0)
    chamber_t = getattr(target_printer, "chamber_temper", 0)
    wifi_sig = getattr(target_printer, "wifi_signal", "")

    nozzle_target_str = (
        f" / {nozzle_target}°C" if isinstance(nozzle_target, (int, float)) and nozzle_target > 0 else ""
    )
    bed_target_str = f" / {bed_target}°C" if isinstance(bed_target, (int, float)) and bed_target > 0 else ""

    chamber_label = "Chamber" if is_en else "Камера"
    chamber_str = f" | 🌡️ <b>{chamber_label}:</b> <code>{chamber_t}°C</code>" if isinstance(chamber_t, (int, float)) and chamber_t > 0 else ""
    wifi_str = f" | 📶 <b>Wi-Fi:</b> <code>{wifi_sig}</code>" if isinstance(wifi_sig, str) and wifi_sig else ""

    if is_en:
        status_txt = (
            f"<b>📊 Printer Status: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>State:</b> <code>{target_printer.gcode_state}</code>{wifi_str}\n"
            f"🔥 <b>Nozzle:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Bed:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Filament Type:</b> <b>{target_printer.filament_type}</b>\n"
            f"📦 <b>Spool Remaining:</b> <b>{target_printer.filament_grams}g</b>\n"
        )
    else:
        status_txt = (
            f"<b>📊 Стан принтера: {target_printer.name}</b>\n\n"
            f"{state_emoji} <b>Стан:</b> <code>{target_printer.gcode_state}</code>{wifi_str}\n"
            f"🔥 <b>Сопло:</b> <code>{target_printer.nozzle_temper}°C{nozzle_target_str}</code> | 🛏️ <b>Стіл:</b> <code>{target_printer.bed_temper}°C{bed_target_str}</code>{chamber_str}\n"
            f"🧵 <b>Тип пластику:</b> <b>{target_printer.filament_type}</b>\n"
            f"📦 <b>Залишок на бабіні:</b> <b>{target_printer.filament_grams}g</b>\n"
        )

    ams_hum = getattr(target_printer, "ams_humidity_idx", 0)
    ams_temp_val = getattr(target_printer, "ams_temp", 0.0)
    if getattr(target_printer, "has_ams", False) and isinstance(ams_hum, int) and ams_hum > 0:
        hum_labels = {
            5: "🟢 Perfectly dry (5/5)" if is_en else "🟢 Ідеально сухо (5/5)",
            4: "🟢 Optimal (4/5)" if is_en else "🟢 Оптимально сухо (4/5)",
            3: "🟡 Moderate (3/5)" if is_en else "🟡 Помірно (3/5)",
            2: "🟠 Humid (2/5)" if is_en else "🟠 Волого (2/5)",
            1: "🔴 Critical (1/5)" if is_en else "🔴 Критично волого (1/5)",
        }
        hum_text = hum_labels.get(ams_hum, f"Level {ams_hum}/5")
        ams_temp_str = f" | 🌡️ {ams_temp_val:.1f}°C" if isinstance(ams_temp_val, (int, float)) and ams_temp_val > 0 else ""
        ams_label = "AMS Humidity" if is_en else "Вологість AMS"
        status_txt += f"💧 <b>{ams_label}:</b> <code>{hum_text}</code>{ams_temp_str}\n"

    hms_res = getattr(target_printer, "hms_resolved", None)
    if isinstance(hms_res, list) and hms_res:
        hms_lines = "\n".join([f"• <code>{h}</code>" for h in hms_res])
        hms_title = "Active HMS Alerts" if is_en else "Активні HMS Сповіщення"
        status_txt += f"\n⚠️ <b>{hms_title}:</b>\n{hms_lines}\n"

    upg_info = getattr(target_printer, "upgrade_state", {})
    if isinstance(upg_info, dict) and upg_info.get("new_version_state") and upg_info.get("ota_new_version_number"):
        ota_title = "Firmware Update Available" if is_en else "Доступне оновлення прошивки"
        status_txt += f"\n🆕 <b>{ota_title}:</b> <code>{upg_info['ota_new_version_number']}</code>\n"

    if target_printer.gcode_state in ["RUNNING", "PAUSE"]:
        model_w = target_printer._current_job_grams or getattr(target_printer, "last_job_grams", 0.0)
        unknown_str = "Unknown" if is_en else "Невідомо"
        weight_str = f"<b>{model_w}g</b>" if model_w > 0 else f"<b>{unknown_str}</b>"
        model_lbl = "Model" if is_en else "Модель"
        weight_lbl = "Model Weight" if is_en else "Вага моделі"
        progress_lbl = "Progress" if is_en else "Прогрес"
        layer_lbl = "Layer" if is_en else "Шар"
        time_rem_lbl = "Time Remaining" if is_en else "Залишилось часу"
        min_lbl = "mins" if is_en else "хв"

        status_txt += (
            f"\n-----------------------------------\n"
            f"📄 <b>{model_lbl}:</b> <code>{target_printer.subtask_name or unknown_str}</code>\n"
            f"⚖️ <b>{weight_lbl}:</b> {weight_str}\n"
            f"⏳ <b>{progress_lbl}:</b> <b>{target_printer.mc_percent}%</b>\n"
            f"🧱 <b>{layer_lbl}:</b> <b>{target_printer.layer_num} / {target_printer.total_layer_num}</b>\n"
            f"⏱️ <b>{time_rem_lbl}:</b> ~<b>{target_printer.mc_remaining_time} {min_lbl}</b>\n"
        )
        if model_w > 0:
            cost_info = target_printer.calculate_job_cost(model_w, target_printer.mc_remaining_time)
            cost_lbl = "Cost" if is_en else "Собівартість"
            fil_lbl = "filament" if is_en else "пластик"
            elec_lbl = "power" if is_en else "світло"
            status_txt += f"💰 <b>{cost_lbl}:</b> <code>{cost_info['total_cost']} UAH</code> <i>({fil_lbl}: {cost_info['filament_cost']}UAH, {elec_lbl}: {cost_info['electricity_cost']}UAH)</i>\n"
            spool_before = round(target_printer.filament_grams + (model_w if target_printer._job_deducted else 0.0), 2)
            if model_w > spool_before:
                deficit = round(model_w - spool_before, 2)
                warn_lbl = "WARNING! Not enough filament!" if is_en else "УВАГА! Недостатньо пластику!"
                status_txt += (
                    f"\n⚠️ <b>{warn_lbl}</b>\n"
                    f"❌ Model weight (<b>{model_w}g</b>) exceeds spool remaining (<b>{spool_before}g</b>).\n"
                    f"🚨 Deficit ~<b>{deficit}g</b>!\n"
                ) if is_en else (
                    f"\n⚠️ <b>УВАГА! Недостатньо пластику!</b>\n"
                    f"❌ Вага моделі (<b>{model_w}g</b>) перевищує залишок (<b>{spool_before}g</b>).\n"
                    f"🚨 Не вистачає ~<b>{deficit}g</b>!\n"
                )
    maint_rem = max(0.0, target_printer.maintenance_interval_hours - target_printer.maintenance_hours_counter)
    runtime_lbl = "Operating time" if is_en else "Напрацювання"
    until_maint_lbl = "hrs to service" if is_en else "до ТО"
    status_txt += (
        f"⏱️ <b>{runtime_lbl}:</b> <b>{target_printer.total_print_hours:.1f}h</b> ({until_maint_lbl}: <b>{maint_rem:.1f}h</b>)\n"
    )
    if getattr(target_printer, "last_job_grams", 0.0) > 0 and target_printer.gcode_state not in ["RUNNING", "PAUSE"]:
        last_weight_lbl = "Last print weight" if is_en else "Остання вага моделі"
        status_txt += f"⚖️ <b>{last_weight_lbl}:</b> <b>{target_printer.last_job_grams}g</b>\n"

    status_txt += (
        f"\n-----------------------------------\n"
        f"🌐 <b>IP:</b> <tg-spoiler>{target_printer.ip}</tg-spoiler>\n"
        f"🔑 <b>Access Code:</b> <tg-spoiler>{target_printer.access_code}</tg-spoiler>\n"
        f"🔢 <b>SN:</b> <tg-spoiler>{target_printer.serial_number}</tg-spoiler>"
    )
    await message.answer(status_txt, parse_mode=ParseMode.HTML)


@router.message(F.text.lower().in_(["🧹 скинути лічильник то", "скинути лічильник то", "провести то", "🧹 reset maintenance", "reset maintenance"]))
async def handle_reset_maintenance(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.reset_maintenance_counter()
    await app.save_printers_config()
    u_lang = user.get("language", "uk")
    await message.answer(
        f"🧹 <b>Лічильник ТО для {html.escape(target_printer.name)} успішно скинуто!</b>\n"
        f"⏱️ Новий відлік до наступного ТО: <b>{target_printer.maintenance_interval_hours} год</b>." if u_lang != "en" else f"🧹 <b>Maintenance counter for {html.escape(target_printer.name)} reset successfully!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang),
    )


@router.message(F.text.lower().in_(["📷 камера", "📷 реальне фото (камера)", "фото", "камера", "📷 camera", "camera"]))
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
            parse_mode=ParseMode.MARKDOWN,
        )
        await msg_wait.delete()
    else:
        await message.answer(
            f"⚠️ *Порт камери недоступний для {target_printer.name}*\n"
            f"Х-хмпф! Перевірте Access Code або закрийте Bambu Handy, Бака!",
            parse_mode=ParseMode.MARKDOWN,
        )
        await msg_wait.delete()


@router.message(F.text.lower().in_(["🎛️ керування принтером", "керування принтером", "🎛️ printer control", "printer control", "керування"]))
async def handle_printer_control_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    await message.answer(
        f"<b>🎛️ Керування принтером: {target_printer.name}</b>" if u_lang != "en" else f"<b>🎛️ Printer Controls: {target_printer.name}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_control_keyboard(target_printer, lang=u_lang),
    )


@router.message(F.text.lower().in_(["🎯 калібрувати", "калібрувати", "🎯 calibrate", "calibrate"]))
async def handle_calibrate_printer(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    u_lang = user.get("language", "uk")
    if target_printer.gcode_state == "RUNNING":
        await message.answer(
            "⚠️ Неможливо калібрувати під час друку!" if u_lang != "en" else "⚠️ Cannot calibrate while printing!",
            reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang),
        )
        return

    ok = target_printer.start_calibration()
    if ok:
        await message.answer(
            f"🎯 <b>Запуск автоматичного калібрування для {html.escape(target_printer.name)}...</b>"
            if u_lang != "en"
            else f"🎯 <b>Starting auto-calibration for {html.escape(target_printer.name)}...</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang),
        )
    else:
        await message.answer(
            "⚠️ Не вдалося відправити команду калібрування."
            if u_lang != "en"
            else "⚠️ Failed to send calibration command.",
            reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang),
        )


@router.message(F.text.lower().in_(["💡 підсвітка", "підсвітка", "💡 light", "light"]))
async def handle_toggle_light(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.toggle_chamber_light("toggle")
    u_lang = user.get("language", "uk")
    await message.answer(
        f"💡 Підсвітка для <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.chamber_light_state.upper()}</b>! 💡" if u_lang != "en" else f"💡 Light for <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.chamber_light_state.upper()}</b>! 💡",
        parse_mode=ParseMode.HTML,
        reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang),
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
    await message.answer(
        f"⚡ <b>Оберіть режим швидкості для {html.escape(target_printer.name)}:</b>\nПоточна швидкість: <b>{target_printer.spd_mag}%</b>" if u_lang != "en" else f"⚡ <b>Select speed mode for {html.escape(target_printer.name)}:</b>\nCurrent speed: <b>{target_printer.spd_mag}%</b>",
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

    lvl_map = {"🐢 Silent (50%)": 1, "🚗 Standard (100%)": 2, "🏎️ Sport (124%)": 3, "🚀 Ludicrous (166%)": 4}
    lvl = lvl_map.get(message.text, 2)
    if target_printer.set_speed_level(lvl):
        await message.answer(
            f"✅ Встановлено режим швидкості: <b>{html.escape(message.text)}</b> для {html.escape(target_printer.name)}! І тільки спробуй щось зламати, Бака! 😤🚀",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(target_printer),
        )
    else:
        await message.answer("⚠️ Не вдалося змінити швидкість (MQTT не підключено).")


@router.message(
    F.text.startswith("🔔 Сповіщення:")
    | F.text.startswith("🔕 Сповіщення:")
    | F.text.startswith("🔔 Notifications:")
    | F.text.startswith("🔕 Notifications:")
)
async def handle_toggle_printer_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    target_printer.notify = not target_printer.notify
    await app.save_printers_config()
    u_lang = user.get("language", "uk")
    status_tsun = (
        "Увімкнено ✅"
        if target_printer.notify
        else "Вимкнено 🔕"
    )
    await message.answer(
        f"Сповіщення для {target_printer.name}: {status_tsun}", reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang)
    )


@router.message(F.text.lower().in_(["🗑️ видалити принтер", "видалити принтер", "🗑️ delete printer", "delete printer"]))
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
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Так, видалити принтер")], [KeyboardButton(text="Ні, скасувати")]],
            resize_keyboard=True,
        ),
    )


@router.message(F.text.lower().in_(["➕ додати принтер", "додати принтер", "➕ add printer", "add printer"]))
async def handle_add_printer_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_p_name"
    user["context_data"]["new_printer"] = {}
    await app.storage.save_user(user)
    await message.answer(
        "Введіть *назву* нового принтера:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Відміна")]], resize_keyboard=True),
    )


@router.message(
    F.func(
        lambda m: (
            m.text
            and (
                m.text.startswith("🖨️ ")
                or any(m.text.lower() == p.name.lower() for p in getattr(m, "_app_printers", {}).values())
            )
        )
    )
)
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
        u_lang = user.get("language", "uk")
        await message.answer(
            f"<b>Керування принтером: {printer.name}</b>\n"
            f"Залишок філаменту: <b>{printer.filament_grams}g</b>" if u_lang != "en" else f"<b>Printer Controls: {printer.name}</b>\nFilament remaining: <b>{printer.filament_grams}g</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_printer_menu_keyboard(printer, lang=u_lang),
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
    u_lang = user.get("language", "uk")
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    # Check cancel / back keywords before processing wizard values
    cancel_keywords = {"відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад", "cancel", "/cancel"}
    if text.lower() in cancel_keywords:
        if state.startswith("add_p_"):
            user["state"] = "idle"
            user.get("context_data", {}).pop("new_printer", None)
            await app.storage.save_user(user)
            await message.answer(
                "Додавання принтера скасовано!" if u_lang != "en" else "Printer creation cancelled!",
                reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
            )
            return True
        elif state == "confirm_delete_printer":
            user["state"] = "printer_menu" if target_printer else "idle"
            await app.storage.save_user(user)
            kb = get_printer_menu_keyboard(target_printer, lang=u_lang) if target_printer else get_printers_keyboard(app.printers, lang=u_lang)
            await message.answer("Видалення скасовано." if u_lang != "en" else "Deletion cancelled.", reply_markup=kb)
            return True

    # Check printer selection first if text matches a printer
    for p_id, printer in app.printers.items():
        if text == f"🖨️ {printer.name}" or text.lower() == printer.name.lower():
            user["context_data"]["selected_printer_id"] = str(p_id)
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"<b>Керування принтером: {printer.name}</b>\n"
                f"Залишок філаменту: <b>{printer.filament_grams}g</b>" if u_lang != "en" else f"<b>Printer Controls: {printer.name}</b>\nFilament remaining: <b>{printer.filament_grams}g</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_menu_keyboard(printer, lang=u_lang),
            )
            return True

    if state == "confirm_delete_printer" and target_printer:
        if text.lower() in ["так, видалити принтер", "yes, delete printer"]:
            target_printer.destroy()
            del app.printers[target_printer.id]
            await app.save_printers_config()
            user["state"] = "idle"
            user["context_data"] = {}
            await app.storage.save_user(user)
            await message.answer("🗑️ Принтер успішно видалено!" if u_lang != "en" else "🗑️ Printer deleted successfully!", reply_markup=get_printers_keyboard(app.printers, lang=u_lang))
        else:
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer("Видалення скасовано." if u_lang != "en" else "Deletion cancelled.", reply_markup=get_printer_menu_keyboard(target_printer, lang=u_lang))
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
        p_obj.init_mqtt(asyncio.get_running_loop())
        app.printers[p_obj.id] = p_obj
        await app.save_printers_config()

        user["state"] = "idle"
        user["context_data"] = {}
        await app.storage.save_user(user)
        await message.answer(
            "✅ *Принтер успішно збережено!*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_printers_keyboard(app.printers),
        )
        return True

    return False
