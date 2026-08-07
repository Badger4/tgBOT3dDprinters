"""
Filament and spool management (AMS slots, warehouse spools, manual weight/price edits).
"""
import html
import uuid
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

from bot.keyboards import (
    get_filament_menu_keyboard,
    get_spools_keyboard,
    get_ams_slots_keyboard,
    get_printer_menu_keyboard,
    get_main_keyboard,
)
from utils.math_eval import safe_eval_math

router = Router()

def extract_filament_type_from_name(name: str) -> str:
    import re
    types = [
        "PLA+", "PLA-CF", "PLA", "PETG-CF", "PETG", "PET",
        "ABS-GF", "ABS", "ASA", "TPU-95A", "TPU",
        "PPA-CF", "PA-CF", "PA6-CF", "PA", "PC", "HIPS", "PVA"
    ]
    name_upper = name.upper()
    for t in types:
        pattern = r'(?:\b|_)' + re.escape(t) + r'(?:\b|_)'
        if re.search(pattern, name_upper):
            return t
    words = name.strip().split()
    return words[0] if words else name.strip()

def parse_slot_key_from_text(text: str) -> str:
    clean = text.lower()
    if "a1" in clean or "slot 1" in clean:
        return "0"
    elif "a2" in clean or "slot 2" in clean:
        return "1"
    elif "a3" in clean or "slot 3" in clean:
        return "2"
    elif "a4" in clean or "slot 4" in clean:
        return "3"
    elif "зовнішн" in clean or "vt" in clean:
        return "255"
    return "0"

@router.message(F.text.lower().in_(["🧵 філамент", "редагувати філамент", "філамент"]))
async def handle_filament_menu(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    await message.answer(
        f"🧵 <b>Менеджер Філаменту для {html.escape(target_printer.name)}</b>\n"
        f"📦 Поточний залишок: <b>{target_printer.filament_grams}g</b>\n"
        f"🧵 Тип: <b>{html.escape(target_printer.filament_type)}</b>\n"
        f"💰 Ціна за 1 кг: <b>{target_printer.price_per_kg} грн</b>\n\n"
        f"Оберіть дію:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_menu_keyboard()
    )

@router.message(F.text.lower().in_(["🌈 слоти ams", "слоти ams", "ams"]))
async def handle_ams_slots(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    if not target_printer.ams_units:
        await message.answer(
            f"<b>🌈 Модуль AMS для {html.escape(target_printer.name)}</b>\n\n"
            f"⚠️ <i>Дані AMS оновлюються або модуль AMS не підключено.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    hum_map = {
        1: "🟢 Рівень 1 (Сухо)",
        2: "🟢 Рівень 2 (Норма)",
        3: "🟡 Рівень 3 (Помірна вологість)",
        4: "🟠 Рівень 4 (Волого - потрібна сушка)",
        5: "🔴 Рівень 5 (Дуже волого - замініть десикант)"
    }
    hum_str = hum_map.get(target_printer.ams_humidity_idx, f"Рівень {target_printer.ams_humidity_idx}")

    ams_txt = (
        f"<b>🌈 Модуль AMS — {html.escape(target_printer.name)}</b>\n"
        f"Х-хмпф! Ось твої слоти AMS... Тільки не переплутай нитки, Бака! 😤\n"
        f"💧 <b>Вологість в AMS:</b> {hum_str}\n"
        f"🌡️ <b>Температура AMS:</b> {target_printer.ams_temp}°C\n"
        f"-----------------------------------\n\n"
    )

    for u_idx, unit in enumerate(target_printer.ams_units, 1):
        ams_letter = chr(64 + u_idx) if 1 <= u_idx <= 26 else f"U{u_idx}"
        trays = unit.get("tray", [])
        for t in trays:
            t_id = t.get("id", "0")
            t_type = t.get("tray_type", "Порожньо")
            t_sub = t.get("tray_sub_brands", "")
            t_color = t.get("tray_color", "FFFFFF")

            raw_rem = t.get("remain")
            try:
                t_rem = int(raw_rem) if raw_rem is not None else -1
            except (ValueError, TypeError):
                t_rem = -1

            try:
                slot_num = (int(t_id) % 4) + 1
            except (ValueError, TypeError):
                slot_num = t_id

            is_active = (str(t_id) == str(target_printer.active_ams_tray))
            active_mark = " <b>[⚡ АКТИВНИЙ]</b>" if is_active else ""

            slot_w = target_printer.get_slot_grams(t_id)
            if t_rem >= 0:
                rem_str = f"~{slot_w}g ({t_rem}%)"
            else:
                rem_str = f"~{slot_w}g"

            ams_txt += (
                f"<b>Слот {ams_letter}{slot_num}:</b> 🧵 <b>{html.escape(str(t_type))}</b> {html.escape(str(t_sub))}{active_mark}\n"
                f"   🎨 Колір: <code>#{str(t_color)[:6]}</code> | 📊 Залишок: <b>{rem_str}</b>\n\n"
            )

    ams_txt += (
        f"-----------------------------------\n"
        f"ℹ️ <b>Довідка:</b>\n"
        f"• <b>Залишок філаменту:</b> відраховується від 1000g і автоматично зменшується ботом відповідно до ваги моделей."
    )

    await message.answer(ams_txt, parse_mode=ParseMode.HTML)

@router.message(F.text == "📦 Обрати котушку зі складу")
async def handle_select_spool_warehouse(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На складі немає котушок. Додайте нову котушку кнопкою ➕ Нова котушка.")
        return
    user["state"] = "select_spool_from_db"
    await app.storage.save_user(user)
    await message.answer("📦 <b>Оберіть котушку зі складу:</b>", parse_mode=ParseMode.HTML, reply_markup=get_spools_keyboard(spools))

@router.message(F.text == "✏️ Ручне введення ваги")
async def handle_manual_weight_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "edit_filament_weight"
    await app.storage.save_user(user)
    await message.answer(f"Введіть нову залишкову вагу філаменту (в грамах) для {html.escape(target_printer.name)}:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))

@router.message(F.text == "💰 Ціна 1 кг (Грн)")
async def handle_manual_price_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "edit_filament_price"
    await app.storage.save_user(user)
    await message.answer(f"Введіть вартість 1 кг пластику у грн (поточна: {target_printer.price_per_kg} грн):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))

@router.message(F.text == "✏️ Редагувати котушку")
async def handle_edit_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На складі немає котушок для редагування.")
        return
    user["state"] = "select_spool_to_edit"
    await app.storage.save_user(user)
    await message.answer("✏️ <b>Оберіть котушку для редагування зі складу:</b>", parse_mode=ParseMode.HTML, reply_markup=get_spools_keyboard(spools))

@router.message(F.text == "🗑️ Видалити котушку")
async def handle_delete_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На складі немає котушок для видалення.")
        return
    user["state"] = "select_spool_to_delete"
    await app.storage.save_user(user)
    await message.answer("🗑️ <b>Оберіть котушку для видалення зі складу:</b>", parse_mode=ParseMode.HTML, reply_markup=get_spools_keyboard(spools))

@router.message(F.text == "➕ Нова котушка")
async def handle_add_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_spool_name"
    user["context_data"]["new_spool"] = {}
    await app.storage.save_user(user)
    await message.answer("Введіть назву котушки (наприклад: <code>eSUN PLA+ Black</code>):", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))

@router.message(F.func(lambda m: True))
async def handle_filament_states(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""
    ctx_data = user.get("context_data", {})
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if state == "edit_filament_weight" and target_printer:
        val = safe_eval_math(text)
        if val is not None:
            user["context_data"]["pending_weight"] = val
            user["state"] = "select_slot_for_weight"
            await app.storage.save_user(user)
            await message.answer(
                f"📍 **Оберіть слот AMS для призначення ваги {val}g:**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_ams_slots_keyboard(target_printer)
            )
        else:
            await message.answer("Будь ласка, введіть коректне число у грамах.")
        return True

    if state == "select_slot_for_weight" and target_printer:
        val = ctx_data.get("pending_weight")
        if val is not None:
            slot_key = parse_slot_key_from_text(text)
            slot_label = "A1" if slot_key == "0" else "A2" if slot_key == "1" else "A3" if slot_key == "2" else "A4" if slot_key == "3" else "Зовнішній (VT)"
            
            if target_printer.gcode_state == "RUNNING" and target_printer._current_job_grams > 0 and slot_key == target_printer.get_active_slot_key():
                deducted_val = round(val - target_printer._current_job_grams, 2)
                target_printer.set_slot_grams(deducted_val, slot_key)
                target_printer._job_deducted = True
                msg_note = f" (враховано поточний друк {target_printer._current_job_grams}g ➔ {deducted_val}g)"
            else:
                target_printer.set_slot_grams(val, slot_key)
                msg_note = ""

            await app.save_printers_config()
            user["state"] = "printer_menu"
            user["context_data"].pop("pending_weight", None)
            await app.storage.save_user(user)
            await message.answer(
                f"✅ **Залишок для Слоту {slot_label} оновлено: {target_printer.get_slot_grams(slot_key)}g**{msg_note}!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_printer_menu_keyboard(target_printer)
            )
        return True

    if state == "select_spool_from_db" and target_printer:
        spools = await app.storage.load_spools()
        selected_spool = None
        for s_id, s in spools.items():
            s_name = s.get("name", "")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            t1 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            t2 = f"🧵 {s_name} ({s_grams}g)"
            if text in [t1, t2, s_name] or s_name in text:
                selected_spool = s
                break

        if selected_spool:
            user["context_data"]["pending_spool"] = selected_spool
            user["state"] = "select_slot_for_spool"
            await app.storage.save_user(user)
            await message.answer(
                f"📍 <b>Оберіть слот AMS для призначення котушки {html.escape(selected_spool['name'])}:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_ams_slots_keyboard(target_printer)
            )
        else:
            await message.answer("Будь ласка, оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "select_slot_for_spool" and target_printer:
        selected_spool = ctx_data.get("pending_spool")
        if selected_spool:
            slot_key = parse_slot_key_from_text(text)
            slot_label = "A1" if slot_key == "0" else "A2" if slot_key == "1" else "A3" if slot_key == "2" else "A4" if slot_key == "3" else "Зовнішній (VT)"
            val = float(selected_spool.get("remaining_grams", 1000.0))

            if target_printer.gcode_state == "RUNNING" and target_printer._current_job_grams > 0 and slot_key == target_printer.get_active_slot_key():
                target_printer.set_slot_grams(val - target_printer._current_job_grams, slot_key)
                target_printer._job_deducted = True
            else:
                target_printer.set_slot_grams(val, slot_key)
                target_printer._job_deducted = False

            if slot_key == target_printer.get_active_slot_key():
                target_printer.filament_type = selected_spool.get("type", target_printer.filament_type)
                target_printer.price_per_kg = float(selected_spool.get("price_uah", target_printer.price_per_kg))
                target_printer.active_spool_id = selected_spool["id"]

            await app.save_printers_config()

            user["state"] = "printer_menu"
            user["context_data"].pop("pending_spool", None)
            await app.storage.save_user(user)
            await message.answer(
                f"✅ **Призначено котушку {html.escape(selected_spool['name'])} ({target_printer.get_slot_grams(slot_key)}g) на Слот {slot_label}!**",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_menu_keyboard(target_printer)
            )
        return True

    if state == "edit_filament_price" and target_printer:
        val = safe_eval_math(text)
        if val is not None and val > 0:
            target_printer.price_per_kg = val
            await app.save_printers_config()
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(f"✅ Вартість пластику оновлено: <b>{val} грн/кг</b>", parse_mode=ParseMode.HTML, reply_markup=get_printer_menu_keyboard(target_printer))
        else:
            await message.answer("Будь ласка, введіть число більше 0.")
        return True

    if state == "add_spool_name":
        user["context_data"]["new_spool"]["name"] = text
        detected_type = extract_filament_type_from_name(text)
        user["context_data"]["new_spool"]["type"] = detected_type
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)
        await message.answer(
            f"Введіть початкову вагу котушки в грамах (наприклад <code>1000</code>).\n"
            f"🧵 Автоматично визначений тип пластику: <b>{html.escape(detected_type)}</b>",
            parse_mode=ParseMode.HTML
        )
        return True

    if state == "add_spool_grams":
        val = safe_eval_math(text) or 1000.0
        user["context_data"]["new_spool"]["remaining_grams"] = val
        user["context_data"]["new_spool"]["total_grams"] = val
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)
        await message.answer("Введіть ціну котушки в грн (наприклад <code>650</code>):", parse_mode=ParseMode.HTML)
        return True

    if state == "add_spool_price":
        price_val = safe_eval_math(text) or 650.0
        new_s = user["context_data"].get("new_spool", {})
        spool_id = f"spool_{str(uuid.uuid4())[:8]}"
        new_s["id"] = spool_id
        new_s["price_uah"] = price_val
        if not new_s.get("type"):
            new_s["type"] = extract_filament_type_from_name(new_s.get("name", "PLA"))
        new_s["color"] = "Standart"

        spools = await app.storage.load_spools()
        spools[spool_id] = new_s
        await app.storage.save_spools(spools)

        user["state"] = "printer_menu" if target_printer else "idle"
        await app.storage.save_user(user)
        kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
        await message.answer(
            f"✅ Нову котушку <b>{html.escape(new_s['name'])}</b> (Тип: <b>{html.escape(new_s['type'])}</b>, {new_s['remaining_grams']}g, {price_val} грн) додано на склад!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
        return True

    if state == "select_spool_to_edit":
        spools = await app.storage.load_spools()
        selected_spool = None
        for s_id, s in spools.items():
            s_name = s.get("name", "")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            t1 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            t2 = f"🧵 {s_name} ({s_grams}g)"
            if text in [t1, t2, s_name] or s_name in text:
                selected_spool = s
                break

        if selected_spool:
            user["context_data"]["edit_spool"] = selected_spool
            user["state"] = "select_spool_field"
            await app.storage.save_user(user)
            field_kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="📝 Назву / Тип"), KeyboardButton(text="⚖️ Залишкову вагу (g)")],
                [KeyboardButton(text="💰 Вартість 1 кг (грн)")],
                [KeyboardButton(text="⬅️ Назад")]
            ], resize_keyboard=True)
            await message.answer(
                f"📝 <b>Оберіть параметр для редагування котушки {html.escape(selected_spool['name'])}:</b>\n"
                f"• Поточний залишок: {selected_spool.get('remaining_grams', 1000.0)}g\n"
                f"• Поточна ціна: {selected_spool.get('price_uah', 650.0)} грн",
                parse_mode=ParseMode.HTML,
                reply_markup=field_kb
            )
        else:
            await message.answer("Будь ласка, оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "select_spool_field":
        spool = ctx_data.get("edit_spool")
        if not spool:
            user["state"] = "printer_menu" if target_printer else "idle"
            await app.storage.save_user(user)
            return True

        if text == "📝 Назву / Тип":
            user["state"] = "edit_spool_name"
            await app.storage.save_user(user)
            await message.answer(f"Введіть нову назву для котушки <b>{html.escape(spool['name'])}</b>:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))
        elif text == "⚖️ Залишкову вагу (g)":
            user["state"] = "edit_spool_grams"
            await app.storage.save_user(user)
            await message.answer(f"Введіть новий залишок ваги (в грамах) для <b>{html.escape(spool['name'])}</b>:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))
        elif text == "💰 Вартість 1 кг (грн)":
            user["state"] = "edit_spool_price"
            await app.storage.save_user(user)
            await message.answer(f"Введіть нову вартість 1 кг (в грн) для <b>{html.escape(spool['name'])}</b>:", parse_mode=ParseMode.HTML, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True))
        else:
            await message.answer("Будь ласка, оберіть кнопкою параметр для редагування.")
        return True

    if state == "edit_spool_name":
        spool = ctx_data.get("edit_spool")
        if spool:
            spools = await app.storage.load_spools()
            s_id = spool["id"]
            if s_id in spools:
                spools[s_id]["name"] = text
                spools[s_id]["type"] = extract_filament_type_from_name(text)
                await app.storage.save_spools(spools)
                user["state"] = "printer_menu" if target_printer else "idle"
                user["context_data"].pop("edit_spool", None)
                await app.storage.save_user(user)
                kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
                await message.answer(f"✅ Назву та тип оновлено: <b>{html.escape(text)}</b> (Тип: <b>{spools[s_id]['type']}</b>)!", parse_mode=ParseMode.HTML, reply_markup=kb)
        return True

    if state == "edit_spool_grams":
        spool = ctx_data.get("edit_spool")
        val = safe_eval_math(text)
        if spool and val is not None:
            spools = await app.storage.load_spools()
            s_id = spool["id"]
            if s_id in spools:
                spools[s_id]["remaining_grams"] = val
                spools[s_id]["total_grams"] = max(val, float(spools[s_id].get("total_grams", 1000.0)))
                await app.storage.save_spools(spools)
                user["state"] = "printer_menu" if target_printer else "idle"
                user["context_data"].pop("edit_spool", None)
                await app.storage.save_user(user)
                kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
                await message.answer(f"✅ Залишок ваги для <b>{html.escape(spool['name'])}</b> оновлено: <b>{val}g</b>!", parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await message.answer("Будь ласка, введіть коректне число в грамах.")
        return True

    if state == "edit_spool_price":
        spool = ctx_data.get("edit_spool")
        val = safe_eval_math(text)
        if spool and val is not None and val > 0:
            spools = await app.storage.load_spools()
            s_id = spool["id"]
            if s_id in spools:
                spools[s_id]["price_uah"] = val
                await app.storage.save_spools(spools)
                user["state"] = "printer_menu" if target_printer else "idle"
                user["context_data"].pop("edit_spool", None)
                await app.storage.save_user(user)
                kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
                await message.answer(f"✅ Вартість для <b>{html.escape(spool['name'])}</b> оновлено: <b>{val} грн/кг</b>!", parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await message.answer("Будь ласка, введіть число більше 0.")
        return True

    if state == "select_spool_to_delete":
        spools = await app.storage.load_spools()
        selected_spool = None
        for s_id, s in spools.items():
            s_name = s.get("name", "")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            t1 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            t2 = f"🧵 {s_name} ({s_grams}g)"
            if text in [t1, t2, s_name] or s_name in text:
                selected_spool = s
                break

        if selected_spool:
            user["context_data"]["delete_spool"] = selected_spool
            user["state"] = "confirm_delete_spool"
            await app.storage.save_user(user)
            confirm_kb = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text="✅ Так, видалити котушку")],
                [KeyboardButton(text="❌ Скасувати")]
            ], resize_keyboard=True)
            await message.answer(
                f"⚠️ <b>Ви впевнені, що бажаєте видалити котушку з зі склада?</b>\n"
                f"📦 <b>{html.escape(selected_spool['name'])}</b> ({selected_spool.get('remaining_grams', 1000.0)}g)",
                parse_mode=ParseMode.HTML,
                reply_markup=confirm_kb
            )
        else:
            await message.answer("Будь ласка, оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "confirm_delete_spool":
        selected_spool = ctx_data.get("delete_spool")
        if text == "✅ Так, видалити котушку" and selected_spool:
            spools = await app.storage.load_spools()
            s_id = selected_spool["id"]
            if s_id in spools:
                del spools[s_id]
                await app.storage.save_spools(spools)
            user["state"] = "printer_menu" if target_printer else "idle"
            user["context_data"].pop("delete_spool", None)
            await app.storage.save_user(user)
            kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
            await message.answer(f"🗑️ Котушку <b>{html.escape(selected_spool['name'])}</b> успішно видалено зі склада!", parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            user["state"] = "printer_menu" if target_printer else "idle"
            user["context_data"].pop("delete_spool", None)
            await app.storage.save_user(user)
            kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
            await message.answer("Видалення котушки скасовано.", reply_markup=kb)
        return True

    return False
