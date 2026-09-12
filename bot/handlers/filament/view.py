"""
Filament warehouse view & RFID sync handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.keyboards import get_filament_menu_keyboard, get_single_printer_filament_keyboard
from utils.filament_utils import get_color_emoji, get_color_display_name

router = Router()


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
            "🧵 filament",
            "filament",
        ]
    )
)
async def handle_filament_menu(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    spools = await app.storage.load_spools()
    spool_list = list(spools.values())
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid and hasattr(app, "printers") else None
    msg_low = message.text.strip().lower() if message.text else ""
    is_printer_filament_btn = msg_low in ["🧵 філамент", "філамент", "🧵 filament", "filament"]

    if target_printer and is_printer_filament_btn:
        active_k = target_printer.get_active_slot_key() if hasattr(target_printer, "get_active_slot_key") else "254"
        active_grams = target_printer.get_slot_grams(active_k) if hasattr(target_printer, "get_slot_grams") else getattr(target_printer, "filament_grams", 0.0)
        try:
            active_grams_val = float(active_grams)
        except (TypeError, ValueError):
            active_grams_val = 0.0
        has_active_spool = active_grams_val > 0.0

        fil_grams_str = f"<code>{active_grams_val}g</code>" if has_active_spool else ("<i>Порожньо</i>" if u_lang != "en" else "<i>Empty</i>")
        fil_type_str = f"<code>{target_printer.filament_type}</code>" if (has_active_spool and target_printer.filament_type and target_printer.filament_type not in ["Невизначено", "None", "", "Порожньо", "Empty"]) else "<i>—</i>"

        txt = (
            f"<b>🧵 Філамент & AMS — {html.escape(target_printer.name)}</b>\n\n"
            f"📦 <b>Залишок нитки на бабіні:</b> {fil_grams_str}\n"
            f"🎨 <b>Тип пластику:</b> {fil_type_str}\n\n"
        ) if u_lang != "en" else (
            f"<b>🧵 Filament & AMS — {html.escape(target_printer.name)}</b>\n\n"
            f"📦 <b>Spool Remaining:</b> {fil_grams_str}\n"
            f"🎨 <b>Filament Type:</b> {fil_type_str}\n\n"
        )

        has_ams = bool(getattr(target_printer, "has_ams", False))
        if has_ams:
            ams_hum = getattr(target_printer, "ams_humidity_idx", 0)
            ams_temp_val = getattr(target_printer, "ams_temp", 0.0)
            hum_map = {
                5: "🟢 5/5 (Ідеально сухо)" if u_lang != "en" else "🟢 5/5 (Perfectly Dry)",
                4: "🟢 4/5 (Оптимально сухо)" if u_lang != "en" else "🟢 4/5 (Optimal)",
                3: "🟡 3/5 (Помірна вологість)" if u_lang != "en" else "🟡 3/5 (Moderate)",
                2: "🟠 2/5 (Волого)" if u_lang != "en" else "🟠 2/5 (Humid)",
                1: "🔴 1/5 (Критично волого)" if u_lang != "en" else "🔴 1/5 (Critical)",
            }
            hum_text = hum_map.get(ams_hum, "—")
            temp_str = f" | 🌡️ {ams_temp_val:.1f}°C" if isinstance(ams_temp_val, (int, float)) and ams_temp_val > 0 else ""
            txt += (
                f"💧 <b>Вологість AMS:</b> {hum_text}{temp_str}\n"
                f"-----------------------------------\n"
                f"<b>🌈 AMS Slots:</b>\n\n"
            ) if u_lang != "en" else (
                f"💧 <b>AMS Humidity:</b> {hum_text}{temp_str}\n"
                f"-----------------------------------\n"
                f"<b>🌈 AMS Slots:</b>\n\n"
            )

            active_key = target_printer.get_active_slot_key() if hasattr(target_printer, "get_active_slot_key") else "254"
            slots = getattr(target_printer, "ams_slots", {})
            slot_keys = ["0", "1", "2", "3", "254"]
            slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}
        else:
            txt += (
                f"<b>🧵 Зовнішній Філамент (Без AMS):</b>\n\n" if u_lang != "en" else f"<b>🧵 External Spool (No AMS):</b>\n\n"
            )
            active_key = target_printer.get_active_slot_key() if hasattr(target_printer, "get_active_slot_key") else "254"
            slots = getattr(target_printer, "ams_slots", {})
            slot_keys = ["254"]
            slot_names = {"254": "VT"}

        for k in slot_keys:
            s_name = slot_names[k]
            assigned = next(
                (s for s in spool_list if s.get("assigned_printer_id") == target_printer.id and str(s.get("assigned_slot_key")) in [str(k), "255" if k == "254" else str(k)]),
                None,
            )
            tray_info = (getattr(target_printer, "ams_trays_info", {}) or {}).get(str(k), {})
            is_empty_tray = tray_info.get("empty", True) if tray_info else True
            raw_g = float(assigned.get("remaining_grams", slots.get(k, 1000.0))) if assigned else float(slots.get(k, 0.0 if is_empty_tray else 1000.0))

            has_filament = (raw_g > 0.0) and (bool(assigned) or (not is_empty_tray and bool(tray_info.get("type"))))

            if has_filament:
                if assigned:
                    sp_title = f"{html.escape(assigned.get('name', ''))} ({html.escape(assigned.get('type', ''))})"
                    sp_cap = float(assigned.get("initial_grams") or assigned.get("total_grams") or max(1000.0, raw_g))
                else:
                    t_type = html.escape(str(tray_info.get("type", "")))
                    t_sub = html.escape(str(tray_info.get("sub_brands", "")))
                    sp_title = f"Bambu {t_type} {t_sub}".strip()
                    sp_cap = max(1000.0, raw_g)

                is_act = (str(k) == str(active_key) or (k == "254" and str(active_key) in ["254", "255"])) and has_filament
                act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""
                pct = min(100, max(0, int((raw_g / sp_cap) * 100))) if sp_cap > 0 else 0
                txt += f"   • <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
            else:
                empty_label = "Порожньо" if u_lang != "en" else "Empty"
                txt += f"   • <b>{s_name}</b>: {empty_label}\n"

        await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_single_printer_filament_keyboard(lang=u_lang))
        return

    user["state"] = "idle"
    await app.storage.save_user(user)

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
            p_has_ams = bool(getattr(p, "has_ams", False))
            if p_has_ams:
                hum_text = hum_map.get(getattr(p, "ams_humidity_idx", 0), "—")
                ams_temp_val = getattr(p, "ams_temp", 0.0)
                temp_str = f" | 🌡️ {ams_temp_val:.1f}°C" if isinstance(ams_temp_val, (int, float)) and ams_temp_val > 0 else ""
                txt += f"🖨️ <b>{html.escape(p.name)}</b> (💧 {hum_text}{temp_str})\n"
            else:
                txt += f"🖨️ <b>{html.escape(p.name)}</b> (Зовнішня котушка)\n" if u_lang != "en" else f"🖨️ <b>{html.escape(p.name)}</b> (External Spool)\n"

            has_ams = p_has_ams
            active_key = p.get_active_slot_key() if hasattr(p, "get_active_slot_key") else "254"
            slots = getattr(p, "ams_slots", {})
            slot_keys = ["0", "1", "2", "3", "254"] if has_ams else ["254"]
            slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}

            for k in slot_keys:
                s_name = slot_names[k]
                assigned = next(
                    (s for s in spool_list if s.get("assigned_printer_id") == p.id and str(s.get("assigned_slot_key")) == str(k)),
                    None,
                )
                tray_info = (getattr(p, "ams_trays_info", {}) or {}).get(str(k), {})
                is_empty_tray = tray_info.get("empty", True) if tray_info else True
                raw_g = float(assigned.get("remaining_grams", slots.get(k, 1000.0))) if assigned else float(slots.get(k, 0.0 if is_empty_tray else 1000.0))

                has_filament = (raw_g > 0.0) and (bool(assigned) or (not is_empty_tray and bool(tray_info.get("type"))))

                if has_filament:
                    if assigned:
                        sp_title = f"{html.escape(assigned.get('name', ''))} ({html.escape(assigned.get('type', ''))})"
                        sp_cap = float(assigned.get("initial_grams") or assigned.get("total_grams") or max(1000.0, raw_g))
                    else:
                        t_type = html.escape(str(tray_info.get("type", "")))
                        t_sub = html.escape(str(tray_info.get("sub_brands", "")))
                        sp_title = f"Bambu {t_type} {t_sub}".strip()
                        sp_cap = max(1000.0, raw_g)

                    is_act = (str(k) == str(active_key)) and has_filament
                    act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""
                    pct = min(100, max(0, int((raw_g / sp_cap) * 100))) if sp_cap > 0 else 0
                    txt += f"   • <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
                else:
                    empty_label = "Порожньо" if u_lang != "en" else "Empty"
                    txt += f"   • <b>{s_name}</b>: {empty_label}\n"
            txt += "\n"
    else:
        txt += ("⚠️ Принтери не додані.\n\n" if u_lang != "en" else "⚠️ No printers added.\n\n")

    sp_stock_lbl = "📦 <b>Склад Котушок:</b>" if u_lang != "en" else "📦 <b>Spool Stock:</b>"
    unassigned_spools = [s for s in spool_list if not s.get("assigned_printer_id")]
    stock_unit = "pcs." if u_lang == "en" else "шт."
    txt += (
        f"-----------------------------------\n"
        f"{sp_stock_lbl} {len(unassigned_spools)} {stock_unit}\n"
    )

    if unassigned_spools:
        txt += ("<b>Котушки на складі:</b>\n" if u_lang != "en" else "<b>Spools in Stock:</b>\n")
        for s in unassigned_spools[-5:]:
            s_n = html.escape(s.get("name", "Spool" if u_lang == "en" else "Котушка"))
            s_t = html.escape(s.get("type", "PLA"))
            s_g = s.get("remaining_grams", 1000.0)
            s_pr = s.get("price_per_kg") or s.get("price_uah", 0.0)
            c_ico = get_color_emoji(s.get("color_name") or s.get("color", ""))
            c_pfx = f"{c_ico} " if c_ico else ""
            cur_str = "грн/кг" if u_lang != "en" else "UAH/kg"
            txt += f"• {c_pfx}<b>{s_n}</b> ({s_t}) — <b>{s_g}g</b> | {s_pr} {cur_str}\n"
    else:
        txt += (
            "<i>На складі немає вільних котушок (усі встановлені на принтери або склад порожній).</i>\n"
            if u_lang != "en"
            else "<i>No free spools in stock (all mounted or stock is empty).</i>\n"
        )

    await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_filament_menu_keyboard(lang=u_lang))


@router.message(F.text.lower().in_(["🏷️ зчитати rfid котушки", "зчитати rfid котушки", "🏷️ rfid зчитування", "rfid зчитування", "zchytaty rfid", "rfid", "🏷️ read rfid spools", "read rfid spools", "🏷️ rfid sync", "rfid sync"]))
async def handle_rfid_sync(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    added_count = 0
    updated_count = 0

    import uuid
    for p in app.printers.values():
        trays = getattr(p, "ams_trays_info", {}) or {}
        for slot_id, t_info in trays.items():
            if not isinstance(t_info, dict) or t_info.get("empty", True):
                continue

            tag_uid = str(t_info.get("tag_uid") or "").strip()
            if not tag_uid or not tag_uid.replace("0", "") or tag_uid.lower() in ["none", "null", "ffffff"]:
                continue

            t_type = str(t_info.get("type") or "").strip().upper()
            if not t_type or t_type == "UNKNOWN":
                continue

            t_sub = str(t_info.get("sub_brands") or "").strip()
            t_color = str(t_info.get("color") or "#000000")
            remain_pct = t_info.get("remain", -1)

            slot_grams = p.get_slot_grams(slot_id) if hasattr(p, "get_slot_grams") else 1000.0
            if isinstance(remain_pct, (int, float)) and remain_pct > 0:
                rem_g = round((remain_pct / 100.0) * 1000.0, 1)
            elif slot_grams > 0:
                rem_g = float(slot_grams)
            else:
                rem_g = 1000.0

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


@router.message(F.text.lower().in_(["🌈 слоти ams", "слоти ams", "ams", "🌈 ams slots", "ams slots"]))
async def handle_ams_slots(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer("⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери».")
        return

    ams_units = getattr(target_printer, "ams_units", [])
    if not ams_units:
        await message.answer(
            f"<b>🌈 AMS Module for {html.escape(target_printer.name)}</b>\n\n⚠️ <i>AMS data is updating or AMS is not connected.</i>"
            if is_en
            else f"<b>🌈 Модуль AMS для {html.escape(target_printer.name)}</b>\n\n⚠️ <i>Дані AMS оновлюються або модуль AMS не підключено.</i>",
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
    hum_str = hum_map.get(getattr(target_printer, "ams_humidity_idx", 0), f"Level {getattr(target_printer, 'ams_humidity_idx', 0)}")
    temp_val = getattr(target_printer, "ams_temp", 0.0)

    ams_txt = (
        f"<b>🌈 AMS Module — {html.escape(target_printer.name)}</b>\n"
        f"💧 <b>AMS Humidity:</b> {hum_str}\n"
        f"🌡️ <b>AMS Temp:</b> {temp_val}°C\n"
        f"-----------------------------------\n\n"
    ) if is_en else (
        f"<b>🌈 Модуль AMS — {html.escape(target_printer.name)}</b>\n"
        f"💧 <b>Вологість в AMS:</b> {hum_str}\n"
        f"🌡️ <b>Температура AMS:</b> {temp_val}°C\n"
        f"-----------------------------------\n\n"
    )

    for u_idx, unit in enumerate(ams_units, 1):
        ams_letter = chr(64 + u_idx) if 1 <= u_idx <= 26 else f"U{u_idx}"
        trays = unit.get("tray", [])
        for t in trays:
            t_id = t.get("id", "0")
            t_type = t.get("tray_type", "Порожньо" if not is_en else "Empty")
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
                slot_num = 1

            active_mark = " ⚡" if t.get("is_active") else ""
            rem_str = f"{t_rem}%" if t_rem >= 0 else f"~{target_printer.filament_grams}g"

            clean_c = str(t_color)[:6]
            if not clean_c.startswith("#"):
                clean_c = f"#{clean_c}"
            c_name_disp = get_color_display_name(clean_c, lang=u_lang)
            ams_txt += (
                f"<b>Слот {ams_letter}{slot_num}:</b> 🧵 <b>{html.escape(str(t_type))}</b> {html.escape(str(t_sub))}{active_mark}\n"
                f"   🎨 Колір: <b>{c_name_disp}</b> | 📊 Залишок: <b>{rem_str}</b>\n\n"
            )

    await message.answer(ams_txt, parse_mode=ParseMode.HTML)

