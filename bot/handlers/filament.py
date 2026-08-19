"""
Filament and spool management (AMS slots, warehouse spools, manual weight/price edits).
"""

import html
import uuid

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import (
    get_ams_slots_keyboard,
    get_filament_menu_keyboard,
    get_main_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
    get_spool_presets_inline_keyboard,
    get_spools_keyboard,
)
from utils.math_eval import safe_eval_math

router = Router()


def extract_filament_type_from_name(name: str) -> str:
    import re

    types = [
        "PLA+",
        "PLA-CF",
        "PLA",
        "PETG-CF",
        "PETG",
        "PET",
        "ABS-GF",
        "ABS",
        "ASA",
        "TPU-95A",
        "TPU",
        "PPA-CF",
        "PA-CF",
        "PA6-CF",
        "PA",
        "PC",
        "HIPS",
        "PVA",
    ]
    name_upper = name.upper()
    for t in types:
        pattern = r"(?:\b|_)" + re.escape(t) + r"(?:\b|_)"
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


@router.message(
    F.text.lower().in_(
        [
            "📦 склад",
            "склад",
            "🧵 філамент & ams",
            "філамент & ams",
            "🧵 філамент",
            "редагувати філамент",
            "філамент",
            "📦 склад котушок",
            "склад котушок",
            "📦 warehouse",
            "warehouse",
        ]
    )
)
async def handle_filament_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    spools = await app.storage.load_spools()
    spool_list = list(spools.values())
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    txt = (
        "<b>📦 Склад Матеріалів & AMS 3D Ферми</b>\n" if u_lang != "en" else "<b>📦 Materials Stock & AMS Farm</b>\n"
    )
    txt += "-----------------------------------\n"
    txt += "<b>🌈 Принтери & Слоти AMS:</b>\n\n" if u_lang != "en" else "<b>🌈 Printers & AMS Slots:</b>\n\n"

    hum_map = {
        5: "🟢 5/5 (Ідеально сухо)" if u_lang != "en" else "🟢 5/5 (Perfectly Dry)",
        4: "🟢 4/5 (Оптимально сухо)" if u_lang != "en" else "🟢 4/5 (Optimal)",
        3: "🟡 3/5 (Помірна вологість)" if u_lang != "en" else "🟡 3/5 (Moderate)",
        2: "🟠 2/5 (Волого)" if u_lang != "en" else "🟠 2/5 (Humid)",
        1: "🔴 1/5 (Критично волого)" if u_lang != "en" else "🔴 1/5 (Critical)",
    }

    if app.printers:
        for p in app.printers.values():
            has_ams = getattr(p, "has_ams", False) or bool(getattr(p, "ams_units", []))
            if has_ams:
                hum_text = hum_map.get(getattr(p, "ams_humidity_idx", 0), "—")
                ams_temp_val = getattr(p, "ams_temp", 0.0)
                temp_str = f" | 🌡️ {ams_temp_val:.1f}°C" if isinstance(ams_temp_val, (int, float)) and ams_temp_val > 0 else ""
                txt += f"🖨️ <b>{html.escape(p.name)}</b> (💧 {hum_text}{temp_str})\n"
            else:
                txt += f"🖨️ <b>{html.escape(p.name)}</b>\n"

            has_ams = getattr(p, "has_ams", False)
            active_key = p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "255"
            slots = getattr(p, "ams_slots", {})
            slot_keys = ["0", "1", "2", "3", "255"] if has_ams else ["255"]
            slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "255": "VT"}

            for k in slot_keys:
                s_name = slot_names[k]
                assigned = next(
                    (s for s in spool_list if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == str(k)),
                    None,
                )
                tray_info = (getattr(p, "ams_trays_info", {}) or {}).get(str(k), {})
                is_empty_tray = tray_info.get("empty", True) if tray_info else True
                has_filament = bool(assigned) or (not is_empty_tray and bool(tray_info.get("type")))

                if assigned:
                    sp_title = f"{html.escape(assigned.get('name', ''))} ({html.escape(assigned.get('type', ''))})"
                    raw_g = float(assigned.get("remaining_grams", slots.get(k, 1000.0)))
                elif not is_empty_tray and tray_info.get("type"):
                    t_type = html.escape(str(tray_info.get("type", "")))
                    t_sub = html.escape(str(tray_info.get("sub_brands", "")))
                    sp_title = f"Bambu {t_type} {t_sub}".strip()
                    raw_g = slots.get(k, 1000.0)
                else:
                    sp_title = "Порожньо" if u_lang != "en" else "Empty"
                    raw_g = 0.0

                is_act = (str(k) == str(active_key)) and has_filament
                act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""

                if has_filament:
                    pct = min(100, max(0, int((raw_g / 1000.0) * 100)))
                    txt += f"   • <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
                else:
                    empty_label = "Порожньо" if u_lang != "en" else "Empty"
                    txt += f"   • <b>{s_name}</b>: {empty_label}\n"
            txt += "\n"
    else:
        txt += ("⚠️ Принтери не додані.\n\n" if u_lang != "en" else "⚠️ No printers added.\n\n")

    sp_stock_lbl = "📦 <b>Склад Котушок:</b>" if u_lang != "en" else "📦 <b>Spool Stock:</b>"
    free_sp_lbl = "🔹 Вільних котушок на складі:" if u_lang != "en" else "🔹 Free spools in stock:"
    txt += (
        f"-----------------------------------\n"
        f"{sp_stock_lbl} {len(spool_list)} pcs.\n"
    )

    unassigned_count = len([s for s in spool_list if not s.get("assigned_printer_id")])
    txt += f"{free_sp_lbl} <b>{unassigned_count} pcs.</b>\n\n"

    if spool_list:
        txt += ("<b>Котушки на складі:</b>\n" if u_lang != "en" else "<b>Spools in Stock:</b>\n")
        for s in spool_list[-5:]:
            s_n = html.escape(s.get("name", "Spool" if u_lang == "en" else "Котушка"))
            s_t = html.escape(s.get("type", "PLA"))
            s_g = s.get("remaining_grams", 1000.0)
            s_pr = s.get("price_per_kg") or s.get("price_uah", 0.0)
            st_str = ("🟢 Монтовано" if u_lang != "en" else "🟢 Mounted") if s.get("assigned_printer_id") else ("📦 На складі" if u_lang != "en" else "📦 Stock")
            cur_str = "грн/кг" if u_lang != "en" else "UAH/kg"
            txt += f"• <b>{s_n}</b> ({s_t}) — {s_g}g | {s_pr} {cur_str} [{st_str}]\n"

    await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_filament_menu_keyboard(lang=u_lang))


@router.message(F.text.lower().in_(["🏷️ зчитати rfid котушки", "зчитати rfid котушки", "zchytaty rfid", "rfid", "🏷️ read rfid spools", "read rfid spools"]))
async def handle_rfid_sync(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    added_count = 0
    updated_count = 0

    for p in app.printers.values():
        trays = getattr(p, "ams_trays_info", {}) or {}
        for slot_id, t_info in trays.items():
            if not isinstance(t_info, dict) or t_info.get("empty", True):
                continue

            tag_uid = str(t_info.get("tag_uid") or "").strip()
            if not tag_uid:
                continue

            t_type = str(t_info.get("type") or "PLA").upper()
            t_sub = str(t_info.get("sub_brands") or "").strip()
            t_color = str(t_info.get("color") or "#000000")
            remain_pct = t_info.get("remain", -1)

            slot_grams = p.get_slot_grams(slot_id) if hasattr(p, "get_slot_grams") else 1000.0
            if remain_pct >= 0:
                rem_g = round((remain_pct / 100.0) * 1000.0, 1)
            else:
                rem_g = float(slot_grams)

            # Match existing spool by tag_uid
            existing = next((s for s in spools.values() if s.get("tag_uid") == tag_uid), None)

            if existing:
                existing["remaining_grams"] = rem_g
                existing["assigned_printer_id"] = p.id
                existing["assigned_slot_key"] = str(slot_id)
                spools[existing["id"]] = existing
                updated_count += 1
            else:
                spool_name = f"Bambu {t_type} {t_sub}".strip()
                if not t_sub:
                    spool_name = f"Bambu {t_type} (RFID:{tag_uid[:6]})"
                new_id = str(uuid.uuid4())
                spools[new_id] = {
                    "id": new_id,
                    "name": spool_name,
                    "type": t_type,
                    "color": t_color,
                    "remaining_grams": rem_g,
                    "price_per_kg": 850.0,
                    "assigned_printer_id": p.id,
                    "assigned_slot_key": str(slot_id),
                    "tag_uid": tag_uid,
                    "quantity": 1,
                }
                added_count += 1

    if added_count > 0 or updated_count > 0:
        await app.storage.save_spools(spools)
        msg_txt = (
            f"✅ <b>Auto-read AMS RFID spools!</b>\n\n"
            f"🆕 Added new spools: <b>{added_count} pcs.</b>\n"
            f"🔄 Updated existing: <b>{updated_count} pcs.</b>"
        ) if u_lang == "en" else (
            f"✅ <b>Авто-зчитано RFID котушки AMS!</b>\n\n"
            f"🆕 Додано нових котушок: <b>{added_count} шт.</b>\n"
            f"🔄 Оновлено наявних: <b>{updated_count} шт.</b>"
        )
    else:
        msg_txt = (
            "ℹ️ <b>AMS RFID Sync:</b>\n\n"
            "No new RFID-tagged spools detected in AMS slots."
        ) if u_lang == "en" else (
            "ℹ️ <b>RFID Зчитування AMS:</b>\n\n"
            "У слотах AMS не виявлено нових котушок з RFID-мітками або слоти порожні."
        )

    await message.answer(msg_txt, parse_mode=ParseMode.HTML, reply_markup=get_filament_menu_keyboard(lang=u_lang))


@router.message(F.text.lower().in_(["🔗 встановити на принтер", "встановити на принтер", "🔗 mount to printer", "mount to printer"]))
async def handle_mount_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    available_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
    if not available_spools:
        await message.answer("⚠️ На Складі немає вільних котушок для установки." if u_lang != "en" else "⚠️ No free spools available in warehouse.")
        return

    user["state"] = "select_spool_to_mount"
    await app.storage.save_user(user)
    await message.answer(
        "🔗 <b>Оберіть котушку зі Складу для установки на принтер:</b>" if u_lang != "en" else "🔗 <b>Select spool from stock to mount:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard({s["id"]: s for s in available_spools}, lang=u_lang),
    )


@router.message(F.text.lower().in_(["🔓 зняти з принтера", "зняти з принтера", "🔓 unmount spool", "unmount spool"]))
async def handle_unmount_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    mounted_spools = [s for s in spools.values() if s.get("assigned_printer_id")]
    if not mounted_spools:
        await message.answer("⚠️ Наразі жодної котушки не встановлено на принтери." if u_lang != "en" else "⚠️ No spools currently mounted on printers.")
        return

    user["state"] = "select_spool_to_unmount"
    await app.storage.save_user(user)
    await message.answer(
        "🔓 <b>Оберіть котушку для зняття з принтера:</b>" if u_lang != "en" else "🔓 <b>Select spool to unmount:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard({s["id"]: s for s in mounted_spools}, lang=u_lang),
    )


@router.message(F.text.lower().in_(["🌈 слоти ams", "слоти ams", "ams", "🌈 ams slots", "ams slots"]))
async def handle_ams_slots(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    if not target_printer.ams_units:
        await message.answer(
            f"<b>🌈 AMS Module for {html.escape(target_printer.name)}</b>\n\n⚠️ <i>AMS data is updating or AMS is not connected.</i>" if is_en else f"<b>🌈 Модуль AMS для {html.escape(target_printer.name)}</b>\n\n⚠️ <i>Дані AMS оновлюються або модуль AMS не підключено.</i>",
            parse_mode=ParseMode.HTML,
        )
        return

    hum_map = {
        5: "🟢 Level 5 (Perfectly Dry)" if is_en else "🟢 Рівень 5 (Ідеально сухо)",
        4: "🟢 Level 4 (Optimal Dry)" if is_en else "🟢 Рівень 4 (Оптимально сухо)",
        3: "🟡 Level 3 (Moderate)" if is_en else "🟡 Рівень 3 (Помірна вологість)",
        2: "🟠 Level 2 (Humid - drying required)" if is_en else "🟠 Рівень 2 (Волого - потрібна сушка)",
        1: "🔴 Level 1 (Critical - replace desiccant)" if is_en else "🔴 Рівень 1 (Критично волого - замініть десикант)",
    }
    hum_str = hum_map.get(target_printer.ams_humidity_idx, f"Level {target_printer.ams_humidity_idx}")

    ams_txt = (
        f"<b>🌈 AMS Module — {html.escape(target_printer.name)}</b>\n"
        f"💧 <b>AMS Humidity:</b> {hum_str}\n"
        f"🌡️ <b>AMS Temp:</b> {target_printer.ams_temp}°C\n"
        f"-----------------------------------\n\n"
    ) if is_en else (
        f"<b>🌈 Модуль AMS — {html.escape(target_printer.name)}</b>\n"
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

            is_active = str(t_id) == str(target_printer.active_ams_tray)
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
        "-----------------------------------\n"
        "ℹ️ <b>Довідка:</b>\n"
        "• <b>Залишок філаменту:</b> відраховується від 1000g і автоматично зменшується ботом відповідно до ваги моделей."
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
    await message.answer(
        "📦 <b>Оберіть котушку зі складу:</b>", parse_mode=ParseMode.HTML, reply_markup=get_spools_keyboard(spools)
    )


@router.message(
    F.text.lower().in_(
        [
            "⚖️ змінити залишок ваги", "змінити залишок ваги", "✏️ ручне введення ваги", "ручне введення ваги",
            "✏️ manual weight input", "manual weight input"
        ]
    )
)
async def handle_manual_weight_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "edit_filament_weight"
    await app.storage.save_user(user)
    await message.answer(
        f"Введіть нову залишкову вагу філаменту (в грамах) для {html.escape(target_printer.name)}:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
    )


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
    await message.answer(
        f"Введіть вартість 1 кг пластику у грн (поточна: {target_printer.price_per_kg} грн):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["✏️ редагувати котушку", "редагувати котушку", "✏️ edit spool", "edit spool"]))
async def handle_edit_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На складі немає котушок для редагування.")
        return
    user["state"] = "select_spool_to_edit"
    await app.storage.save_user(user)
    await message.answer(
        "✏️ <b>Оберіть котушку для редагування зі складу:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(spools),
    )


@router.message(F.text.lower().in_(["🗑️ видалити котушку", "видалити котушку", "🗑️ delete spool", "delete spool"]))
async def handle_delete_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    spools = await app.storage.load_spools()
    if not spools:
        await message.answer("⚠️ На складі немає котушок для видалення.")
        return
    user["state"] = "select_spool_to_delete"
    await app.storage.save_user(user)
    await message.answer(
        "🗑️ <b>Оберіть котушку для видалення зі складу:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(spools),
    )


@router.message(F.text.lower().in_(["➕ нова котушка", "нова котушка", "➕ new spool", "new spool"]))
async def handle_add_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "add_spool_name"
    user["context_data"]["new_spool"] = {}
    await app.storage.save_user(user)
    await message.answer(
        "🧵 <b>Додавання нової котушки на Склад</b>\n\n"
        "Оберіть швидкий пресет або введіть власну назву (наприклад: <code>eSUN PLA+ Black</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spool_presets_inline_keyboard(),
    )


@router.callback_query(F.data.startswith("spool_preset_"))
async def handle_spool_preset_callback(callback_query, app):
    preset_key = callback_query.data.replace("spool_preset_", "")
    presets = {
        "bambu_pla_black": {"name": "Bambu PLA Black", "type": "PLA", "price": 850.0, "color": "#000000"},
        "sunlu_pla_white": {"name": "Sunlu PLA White", "type": "PLA", "price": 650.0, "color": "#ffffff"},
        "esun_petg_grey": {"name": "eSUN PETG Grey", "type": "PETG", "price": 700.0, "color": "#808080"},
        "tpu_red": {"name": "TPU 95A Red", "type": "TPU", "price": 950.0, "color": "#ff0000"},
    }
    preset = presets.get(preset_key)
    if not preset:
        await callback_query.answer("Пресет не знайдено!")
        return

    spool_id = str(uuid.uuid4())
    spool_obj = {
        "id": spool_id,
        "name": preset["name"],
        "type": preset["type"],
        "color": preset["color"],
        "remaining_grams": 1000.0,
        "price_per_kg": preset["price"],
        "assigned_printer_id": None,
        "assigned_slot_key": None,
        "quantity": 1,
    }
    spools = await app.storage.load_spools()
    spools[spool_id] = spool_obj
    await app.storage.save_spools(spools)

    chat_id = str(callback_query.message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    await app.storage.save_user(user)

    await callback_query.answer("Котушку додано!")
    await callback_query.message.answer(
        f"✅ <b>Котушку з пресету успішно додано на Склад!</b>\n"
        f"📦 <b>{preset['name']}</b> ({preset['type']}, 1000g) — {preset['price']} грн/кг",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_menu_keyboard(),
    )


FILAMENT_STATES = {
    "edit_filament_weight",
    "select_slot_for_weight",
    "select_spool_from_db",
    "select_slot_for_spool",
    "edit_filament_price",
    "add_spool_name",
    "add_spool_grams",
    "add_spool_price",
    "select_spool_to_edit",
    "select_spool_field",
    "edit_spool_name",
    "edit_spool_grams",
    "edit_spool_price",
    "select_spool_to_delete",
    "confirm_delete_spool",
    "select_spool_to_mount",
    "select_printer_for_mount",
    "select_slot_for_mount",
    "select_spool_to_unmount",
}


async def filament_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") in FILAMENT_STATES


@router.message(filament_state_filter)
async def handle_filament_states(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""
    ctx_data = user.get("context_data", {})
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    # Check cancel / back keywords before processing filament wizard values
    cancel_keywords = {"відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад", "cancel", "/cancel"}
    if text.lower() in cancel_keywords:
        user["state"] = "printer_menu" if target_printer else "idle"
        for k in [
            "new_spool",
            "edit_spool",
            "pending_spool",
            "delete_spool",
            "pending_weight",
            "mount_spool",
            "mount_printer_id",
        ]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        kb = (
            get_printer_menu_keyboard(target_printer)
            if target_printer
            else get_main_keyboard(await app.is_user_admin(chat_id))
        )
        await message.answer("Дію скасовано.", reply_markup=kb)
        return True

    if state == "select_spool_to_mount":
        spools = await app.storage.load_spools()
        selected = None
        for s in spools.values():
            s_name = s.get("name", "")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            t1 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            t2 = f"🧵 {s_name} ({s_grams}g)"
            if text in [t1, t2, s_name] or s_name in text:
                selected = s
                break

        if selected:
            user["context_data"]["mount_spool"] = selected
            user["state"] = "select_printer_for_mount"
            await app.storage.save_user(user)
            await message.answer(
                f"🖨️ <b>Оберіть принтер для установки котушки {html.escape(selected['name'])}:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printers_keyboard(app.printers),
            )
        else:
            await message.answer("Оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "select_printer_for_mount":
        selected_spool = ctx_data.get("mount_spool")
        target_p = None
        for p in app.printers.values():
            if text in [f"🖨️ {p.name}", p.name]:
                target_p = p
                break

        if target_p and selected_spool:
            user["context_data"]["mount_printer_id"] = target_p.id
            user["state"] = "select_slot_for_mount"
            await app.storage.save_user(user)
            await message.answer(
                f"📍 <b>Оберіть слот AMS для {html.escape(target_p.name)}:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_ams_slots_keyboard(target_p),
            )
        else:
            await message.answer("Оберіть принтер зі списку на клавіатурі.")
        return True

    if state == "select_slot_for_mount":
        selected_spool = ctx_data.get("mount_spool")
        p_id = ctx_data.get("mount_printer_id")
        target_p = app.printers.get(p_id) if p_id else None

        if target_p and selected_spool:
            slot_key = parse_slot_key_from_text(text)
            slot_label = (
                "A1"
                if slot_key == "0"
                else "A2"
                if slot_key == "1"
                else "A3"
                if slot_key == "2"
                else "A4"
                if slot_key == "3"
                else "Зовнішній (VT)"
            )

            # Unassign previous spool from this slot
            spools = await app.storage.load_spools()
            for s_id, s in list(spools.items()):
                if s.get("assigned_printer_id") == target_p.id and str(s.get("assigned_slot_key")) == slot_key:
                    s["assigned_printer_id"] = None
                    s["assigned_slot_key"] = None
                    spools[s_id] = s

            # Assign new spool
            target_spool = spools.get(selected_spool["id"])
            if target_spool:
                target_spool["assigned_printer_id"] = target_p.id
                target_spool["assigned_slot_key"] = slot_key
                spools[selected_spool["id"]] = target_spool
                await app.storage.save_spools(spools)

            grams = float(selected_spool.get("remaining_grams", 1000.0))
            target_p.set_slot_grams(grams, slot_id=slot_key)
            if selected_spool.get("type"):
                target_p.filament_type = str(selected_spool.get("type"))
            await app.save_printers_config()

            user["state"] = "idle"
            user["context_data"].pop("mount_spool", None)
            user["context_data"].pop("mount_printer_id", None)
            await app.storage.save_user(user)

            await message.answer(
                f"✅ <b>Котушку {html.escape(selected_spool['name'])} встановлено на {html.escape(target_p.name)} [Слот {slot_label}]!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_menu_keyboard(),
            )
        return True

    if state == "select_spool_to_unmount":
        spools = await app.storage.load_spools()
        selected = None
        for s in spools.values():
            s_name = s.get("name", "")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            t1 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            t2 = f"🧵 {s_name} ({s_grams}g)"
            if text in [t1, t2, s_name] or s_name in text:
                selected = s
                break

        if selected:
            target_spool = spools.get(selected["id"])
            if target_spool:
                target_spool["assigned_printer_id"] = None
                target_spool["assigned_slot_key"] = None
                await app.storage.save_spools(spools)

            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer(
                f"🔓 <b>Котушку {html.escape(selected['name'])} успішно знято та повернуто на Склад!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_menu_keyboard(),
            )
        else:
            await message.answer("Оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "edit_filament_weight" and target_printer:
        val = safe_eval_math(text)
        if val is not None:
            user["context_data"]["pending_weight"] = val
            user["state"] = "select_slot_for_weight"
            await app.storage.save_user(user)
            await message.answer(
                f"📍 **Оберіть слот AMS для призначення ваги {val}g:**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_ams_slots_keyboard(target_printer),
            )
        else:
            await message.answer("Будь ласка, введіть коректне число у грамах.")
        return True

    if state == "select_slot_for_weight" and target_printer:
        val = ctx_data.get("pending_weight")
        if val is not None:
            slot_key = parse_slot_key_from_text(text)
            slot_label = (
                "A1"
                if slot_key == "0"
                else "A2"
                if slot_key == "1"
                else "A3"
                if slot_key == "2"
                else "A4"
                if slot_key == "3"
                else "Зовнішній (VT)"
            )

            if (
                target_printer.gcode_state == "RUNNING"
                and target_printer._current_job_grams > 0
                and slot_key == target_printer.get_active_slot_key()
            ):
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
                reply_markup=get_printer_menu_keyboard(target_printer),
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
                reply_markup=get_ams_slots_keyboard(target_printer),
            )
        else:
            await message.answer("Будь ласка, оберіть котушку зі списку на клавіатурі.")
        return True

    if state == "select_slot_for_spool" and target_printer:
        selected_spool = ctx_data.get("pending_spool")
        if selected_spool:
            slot_key = parse_slot_key_from_text(text)
            slot_label = (
                "A1"
                if slot_key == "0"
                else "A2"
                if slot_key == "1"
                else "A3"
                if slot_key == "2"
                else "A4"
                if slot_key == "3"
                else "Зовнішній (VT)"
            )
            val = float(selected_spool.get("remaining_grams", 1000.0))

            if (
                target_printer.gcode_state == "RUNNING"
                and target_printer._current_job_grams > 0
                and slot_key == target_printer.get_active_slot_key()
            ):
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
                reply_markup=get_printer_menu_keyboard(target_printer),
            )
        return True

    if state == "edit_filament_price" and target_printer:
        val = safe_eval_math(text)
        if val is not None and val > 0:
            target_printer.price_per_kg = val
            await app.save_printers_config()
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"✅ Вартість пластику оновлено: <b>{val} грн/кг</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_menu_keyboard(target_printer),
            )
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
            parse_mode=ParseMode.HTML,
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
        kb = (
            get_printer_menu_keyboard(target_printer)
            if target_printer
            else get_main_keyboard(await app.is_user_admin(chat_id))
        )
        await message.answer(
            f"✅ Нову котушку <b>{html.escape(new_s['name'])}</b> (Тип: <b>{html.escape(new_s['type'])}</b>, {new_s['remaining_grams']}g, {price_val} грн) додано на склад!",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
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
            field_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📝 Назву / Тип"), KeyboardButton(text="⚖️ Залишкову вагу (g)")],
                    [KeyboardButton(text="💰 Вартість 1 кг (грн)")],
                    [KeyboardButton(text="⬅️ Назад")],
                ],
                resize_keyboard=True,
            )
            await message.answer(
                f"📝 <b>Оберіть параметр для редагування котушки {html.escape(selected_spool['name'])}:</b>\n"
                f"• Поточний залишок: {selected_spool.get('remaining_grams', 1000.0)}g\n"
                f"• Поточна ціна: {selected_spool.get('price_uah', 650.0)} грн",
                parse_mode=ParseMode.HTML,
                reply_markup=field_kb,
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
            await message.answer(
                f"Введіть нову назву для котушки <b>{html.escape(spool['name'])}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
            )
        elif text == "⚖️ Залишкову вагу (g)":
            user["state"] = "edit_spool_grams"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть новий залишок ваги (в грамах) для <b>{html.escape(spool['name'])}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
            )
        elif text == "💰 Вартість 1 кг (грн)":
            user["state"] = "edit_spool_price"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть нову вартість 1 кг (в грн) для <b>{html.escape(spool['name'])}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
            )
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
                kb = (
                    get_printer_menu_keyboard(target_printer)
                    if target_printer
                    else get_main_keyboard(await app.is_user_admin(chat_id))
                )
                await message.answer(
                    f"✅ Назву та тип оновлено: <b>{html.escape(text)}</b> (Тип: <b>{spools[s_id]['type']}</b>)!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
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
                kb = (
                    get_printer_menu_keyboard(target_printer)
                    if target_printer
                    else get_main_keyboard(await app.is_user_admin(chat_id))
                )
                await message.answer(
                    f"✅ Залишок ваги для <b>{html.escape(spool['name'])}</b> оновлено: <b>{val}g</b>!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
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
                kb = (
                    get_printer_menu_keyboard(target_printer)
                    if target_printer
                    else get_main_keyboard(await app.is_user_admin(chat_id))
                )
                await message.answer(
                    f"✅ Вартість для <b>{html.escape(spool['name'])}</b> оновлено: <b>{val} грн/кг</b>!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
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
            confirm_kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="✅ Так, видалити котушку")], [KeyboardButton(text="❌ Скасувати")]],
                resize_keyboard=True,
            )
            await message.answer(
                f"⚠️ <b>Ви впевнені, що бажаєте видалити котушку з зі склада?</b>\n"
                f"📦 <b>{html.escape(selected_spool['name'])}</b> ({selected_spool.get('remaining_grams', 1000.0)}g)",
                parse_mode=ParseMode.HTML,
                reply_markup=confirm_kb,
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
            kb = (
                get_printer_menu_keyboard(target_printer)
                if target_printer
                else get_main_keyboard(await app.is_user_admin(chat_id))
            )
            await message.answer(
                f"🗑️ Котушку <b>{html.escape(selected_spool['name'])}</b> успішно видалено зі склада!",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        else:
            user["state"] = "printer_menu" if target_printer else "idle"
            user["context_data"].pop("delete_spool", None)
            await app.storage.save_user(user)
            kb = (
                get_printer_menu_keyboard(target_printer)
                if target_printer
                else get_main_keyboard(await app.is_user_admin(chat_id))
            )
            await message.answer("Видалення котушки скасовано.", reply_markup=kb)
        return True

    return False
