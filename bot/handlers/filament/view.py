"""
Filament warehouse view & RFID sync handlers.
"""

from __future__ import annotations

import html
from typing import Any
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
                    c_val = assigned.get("color_name") or assigned.get("color", "")
                else:
                    t_type = html.escape(str(tray_info.get("type", "")))
                    t_sub = html.escape(str(tray_info.get("sub_brands", "")))
                    sp_title = f"Bambu {t_type} {t_sub}".strip()
                    sp_cap = max(1000.0, raw_g)
                    c_val = str(tray_info.get("color") or tray_info.get("tray_color") or "")

                c_ico = get_color_emoji(c_val) if c_val else ("🧵" if k == "254" else "⚪")
                is_act = (str(k) == str(active_key) or (k == "254" and str(active_key) in ["254", "255"])) and has_filament
                act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""
                pct = min(100, max(0, int((raw_g / sp_cap) * 100))) if sp_cap > 0 else 0
                txt += f"   • {c_ico} <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
            else:
                empty_label = "Порожньо" if u_lang != "en" else "Empty"
                txt += f"   • ⚪ <b>{s_name}</b>: {empty_label}\n"

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
                        c_val = assigned.get("color_name") or assigned.get("color", "")
                    else:
                        t_type = html.escape(str(tray_info.get("type", "")))
                        t_sub = html.escape(str(tray_info.get("sub_brands", "")))
                        sp_title = f"Bambu {t_type} {t_sub}".strip()
                        sp_cap = max(1000.0, raw_g)
                        c_val = str(tray_info.get("color") or tray_info.get("tray_color") or "")

                    c_ico = get_color_emoji(c_val) if c_val else ("🧵" if k == "254" else "⚪")
                    is_act = (str(k) == str(active_key)) and has_filament
                    act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""
                    pct = min(100, max(0, int((raw_g / sp_cap) * 100))) if sp_cap > 0 else 0
                    txt += f"   • {c_ico} <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
                else:
                    empty_label = "Порожньо" if u_lang != "en" else "Empty"
                    txt += f"   • ⚪ <b>{s_name}</b>: {empty_label}\n"
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
                prev_g = float(existing.get("remaining_grams", 0.0))
                existing["remaining_grams"] = rem_g
                existing["assigned_printer_id"] = p.id
                existing["assigned_slot_key"] = str(slot_id)
                spools[existing["id"]] = existing
                updated_count += 1
                if abs(rem_g - prev_g) > 0.01:
                    delta = rem_g - prev_g
                    await app.storage.record_spool_movement(
                        spool_id=existing["id"],
                        spool_name=existing.get("name", "Котушка"),
                        action="refill" if delta > 0 else "manual_edit",
                        weight_change_g=round(delta, 2),
                        prev_weight_g=round(prev_g, 2),
                        new_weight_g=round(rem_g, 2),
                        reason="RFID оновлення ваги (AMS)",
                        user="RFID",
                    )
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
                await app.storage.record_spool_movement(
                    spool_id=new_id,
                    spool_name=spool_name,
                    action="initial_stock",
                    weight_change_g=round(rem_g, 2),
                    prev_weight_g=0.0,
                    new_weight_g=round(rem_g, 2),
                    reason="RFID авто-виявлення (AMS)",
                    user="RFID",
                )

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
        await message.answer("⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»." if not is_en else "⚠️ Please select a printer first in «🖨️ Printers».")
        return

    has_ams = bool(getattr(target_printer, "has_ams", False))
    trays = getattr(target_printer, "ams_trays_info", {}) or {}
    if not isinstance(trays, dict):
        trays = {}

    active_k = target_printer.get_active_slot_key() if hasattr(target_printer, "get_active_slot_key") else "254"
    if callable(active_k):
        try:
            active_k = active_k()
        except Exception:
            active_k = "254"
    active_slot_str = str(active_k) if active_k is not None else "254"

    def format_progress_bar(pct: int, grams: float, length: int = 10) -> str:
        if 0 <= pct <= 100:
            filled = round((pct / 100) * length)
            empty = length - filled
            g_str = f" ({grams:.0f}g)" if grams > 0 else ""
            return f"<code>{'█' * filled}{'░' * empty}</code> <b>{pct}%</b>{g_str}"
        elif grams > 0:
            pct_est = min(100, max(0, int((grams / 1000.0) * 100)))
            filled = round((pct_est / 100) * length)
            empty = length - filled
            return f"<code>{'█' * filled}{'░' * empty}</code> ~{pct_est}% (<b>{grams:.0f}g</b>)"
        return "<b>~</b>"

    # Active feeder line (Nozzle feed status)
    if active_slot_str in ["0", "1", "2", "3"]:
        t_act = trays.get(active_slot_str, {})
        act_col = str(t_act.get("color") or t_act.get("tray_color") or "")
        act_c_emoji = get_color_emoji(act_col)
        act_mat = str(t_act.get("type") or t_act.get("tray_type") or "").strip()
        act_sub = str(t_act.get("sub_brands") or "").strip()
        act_name = f"{act_mat} {act_sub}".strip() if (act_sub and act_sub.lower() not in act_mat.lower()) else act_mat
        if not act_name:
            act_name = "Filament" if is_en else "Філамент"
        slot_label = f"A{int(active_slot_str) + 1}"
        nozzle_feed_str = f"{act_c_emoji} <b>{slot_label}</b> ({html.escape(act_name)}) ⚡"
    elif active_slot_str in ["254", "255"]:
        vt_act = trays.get("254", {})
        vt_col = str(vt_act.get("color") or vt_act.get("tray_color") or "")
        vt_c_emoji = get_color_emoji(vt_col) if vt_col else "🧵"
        vt_mat = str(vt_act.get("type") or vt_act.get("tray_type") or "").strip()
        if not vt_mat:
            f_type = getattr(target_printer, "filament_type", "")
            if f_type and f_type not in ["Невизначено", "None", "", "Порожньо", "Empty"]:
                vt_mat = f_type
            else:
                vt_mat = "External Spool" if is_en else "Зовнішній філамент"
        nozzle_feed_str = f"{vt_c_emoji} <b>VT</b> ({html.escape(vt_mat)}) ⚡"
    else:
        nozzle_feed_str = "<i>Немає активної подачі</i>" if not is_en else "<i>No active feed</i>"

    feed_header = f"🔥 <b>Подача в сопло:</b> {nozzle_feed_str}\n" if not is_en else f"🔥 <b>Nozzle Feed:</b> {nozzle_feed_str}\n"

    def _safe_float(val: Any, default: float = 0.0) -> float:
        if callable(val):
            try:
                val = val()
            except Exception:
                return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    try:
        ams_hum = int(getattr(target_printer, "ams_humidity_idx", 0))
    except (TypeError, ValueError):
        ams_hum = 0
    try:
        ams_temp_val = float(getattr(target_printer, "ams_temp", 0.0))
    except (TypeError, ValueError):
        ams_temp_val = 0.0
    hum_map = {
        5: "🟢 5/5 (Ідеально сухо)" if not is_en else "🟢 5/5 (Perfectly Dry)",
        4: "🟢 4/5 (Оптимально сухо)" if not is_en else "🟢 4/5 (Optimal Dry)",
        3: "🟡 3/5 (Помірна вологість)" if not is_en else "🟡 3/5 (Moderate)",
        2: "🟠 2/5 (Волого — потрібна сушка)" if not is_en else "🟠 2/5 (Humid — drying required)",
        1: "🔴 1/5 (Критично волого — замініть десикант)" if not is_en else "🔴 1/5 (Critical — replace desiccant)",
    }
    hum_str = hum_map.get(ams_hum, f"{ams_hum}/5") if ams_hum > 0 else ""
    temp_str = f" | 🌡️ <b>Температура AMS:</b> <code>{ams_temp_val:.1f}°C</code>" if isinstance(ams_temp_val, (int, float)) and ams_temp_val > 0 else ""
    hum_line = f"💧 <b>Вологість AMS:</b> {hum_str}{temp_str}\n" if (hum_str and not is_en) else (f"💧 <b>AMS Humidity:</b> {hum_str}{temp_str}\n" if hum_str else "")

    if has_ams:
        ams_txt = (
            f"<b>🌈 Модуль AMS — {html.escape(target_printer.name)}</b>\n"
            f"{feed_header}"
            f"{hum_line}"
            f"-----------------------------------\n\n"
        ) if not is_en else (
            f"<b>🌈 AMS Module — {html.escape(target_printer.name)}</b>\n"
            f"{feed_header}"
            f"{hum_line}"
            f"-----------------------------------\n\n"
        )
    else:
        ams_txt = (
            f"<b>🧵 Філамент (Пряма подача) — {html.escape(target_printer.name)}</b>\n"
            f"{feed_header}"
            f"-----------------------------------\n\n"
        ) if not is_en else (
            f"<b>🧵 Filament (Direct Feed) — {html.escape(target_printer.name)}</b>\n"
            f"{feed_header}"
            f"-----------------------------------\n\n"
        )

    ams_units = getattr(target_printer, "ams_units", [])

    if has_ams:
        if ams_units and len(ams_units) > 1:
            # Multi-unit AMS setup (AMS A, AMS B, etc.)
            for u_idx, unit in enumerate(ams_units, 1):
                ams_letter = chr(64 + u_idx) if 1 <= u_idx <= 26 else f"U{u_idx}"
                u_trays = unit.get("tray", [])
                for t in u_trays:
                    t_id = str(t.get("id", "0"))
                    t_type = str(t.get("tray_type") or t.get("type") or "").strip()
                    is_empty = bool(t.get("empty", False)) or (not t_type) or (t_type.lower() == "empty")
                    t_sub = str(t.get("tray_sub_brands") or t.get("sub_brands") or "").strip()
                    t_color = str(t.get("tray_color") or t.get("color") or "")
                    try:
                        slot_num = (int(t_id) % 4) + 1
                    except (ValueError, TypeError):
                        slot_num = 1
                    slot_label = f"{ams_letter}{slot_num}"
                    try:
                        t_rem = int(t.get("remain", -1))
                    except (ValueError, TypeError):
                        t_rem = -1
                    raw_slot_g = target_printer.get_slot_grams(t_id) if hasattr(target_printer, "get_slot_grams") else 0.0
                    slot_g = _safe_float(raw_slot_g)

                    is_act = (t_id == active_slot_str)
                    act_mark = (" ⚡ <i>[У соплі]</i>" if not is_en else " ⚡ <i>[In nozzle]</i>") if is_act else ""

                    if is_empty or (not t_type and slot_g <= 0):
                        ams_txt += f"⚪ <b>Слот {slot_label}:</b> <i>{'Empty' if is_en else 'Порожньо'}</i>{act_mark}\n\n"
                    else:
                        c_emoji = get_color_emoji(t_color)
                        clean_c = str(t_color)[:6]
                        if clean_c and not clean_c.startswith("#"):
                            clean_c = f"#{clean_c}"
                        c_name_disp = get_color_display_name(clean_c or t_color, lang=u_lang)
                        mat_full = f"{t_type} {t_sub}".strip() if (t_sub and t_sub.lower() not in t_type.lower()) else t_type
                        if not mat_full:
                            mat_full = "Filament" if is_en else "Філамент"
                        bar_str = format_progress_bar(t_rem, slot_g)
                        ams_txt += (
                            f"{c_emoji} <b>Слот {slot_label}:</b> <b>{html.escape(mat_full)}</b>{act_mark}\n"
                            f"   🎨 Колір: <b>{c_name_disp}</b>\n"
                            f"   📊 Залишок: {bar_str}\n\n"
                        ) if not is_en else (
                            f"{c_emoji} <b>Slot {slot_label}:</b> <b>{html.escape(mat_full)}</b>{act_mark}\n"
                            f"   🎨 Color: <b>{c_name_disp}</b>\n"
                            f"   📊 Remaining: {bar_str}\n\n"
                        )
        else:
            # Single AMS (A1..A4) - using reliable trays dict (with fallback to ams_units[0])
            for idx in range(4):
                slot_k = str(idx)
                slot_label = f"A{idx + 1}"
                t_info = trays.get(slot_k, {})
                if not t_info and ams_units and len(ams_units) > 0:
                    u_trays = ams_units[0].get("tray", [])
                    if idx < len(u_trays):
                        t_info = u_trays[idx]

                is_empty = t_info.get("empty", True) if t_info else True
                t_type = str(t_info.get("type") or t_info.get("tray_type") or "").strip()
                t_sub = str(t_info.get("sub_brands") or t_info.get("tray_sub_brands") or "").strip()
                t_color = str(t_info.get("color") or t_info.get("tray_color") or "")
                try:
                    t_rem = int(t_info.get("remain", -1))
                except (ValueError, TypeError):
                    t_rem = -1
                raw_slot_g = target_printer.get_slot_grams(slot_k) if hasattr(target_printer, "get_slot_grams") else 0.0
                slot_g = _safe_float(raw_slot_g)

                is_act = (slot_k == active_slot_str)
                act_mark = (" ⚡ <i>[У соплі]</i>" if not is_en else " ⚡ <i>[In nozzle]</i>") if is_act else ""

                if is_empty or (not t_type and slot_g <= 0):
                    ams_txt += f"⚪ <b>Слот {slot_label}:</b> <i>{'Empty' if is_en else 'Порожньо'}</i>{act_mark}\n\n"
                else:
                    c_emoji = get_color_emoji(t_color)
                    clean_c = str(t_color)[:6]
                    if clean_c and not clean_c.startswith("#"):
                        clean_c = f"#{clean_c}"
                    c_name_disp = get_color_display_name(clean_c or t_color, lang=u_lang)
                    mat_full = f"{t_type} {t_sub}".strip() if (t_sub and t_sub.lower() not in t_type.lower()) else t_type
                    if not mat_full:
                        mat_full = "Filament" if is_en else "Філамент"
                    bar_str = format_progress_bar(t_rem, slot_g)
                    ams_txt += (
                        f"{c_emoji} <b>Слот {slot_label}:</b> <b>{html.escape(mat_full)}</b>{act_mark}\n"
                        f"   🎨 Колір: <b>{c_name_disp}</b>\n"
                        f"   📊 Залишок: {bar_str}\n\n"
                        ) if not is_en else (
                        f"{c_emoji} <b>Slot {slot_label}:</b> <b>{html.escape(mat_full)}</b>{act_mark}\n"
                        f"   🎨 Color: <b>{c_name_disp}</b>\n"
                        f"   📊 Remaining: {bar_str}\n\n"
                    )

    # External Spool (VT) row
    vt_info = trays.get("254", {})
    vt_empty = vt_info.get("empty", True) if vt_info else True
    vt_type = str(vt_info.get("type") or vt_info.get("tray_type") or "").strip()
    vt_sub = str(vt_info.get("sub_brands") or vt_info.get("tray_sub_brands") or "").strip()
    vt_color = str(vt_info.get("color") or vt_info.get("tray_color") or "")
    try:
        vt_rem = int(vt_info.get("remain", -1))
    except (ValueError, TypeError):
        vt_rem = -1
    raw_vt_g = target_printer.get_slot_grams("254") if hasattr(target_printer, "get_slot_grams") else 0.0
    vt_grams = _safe_float(raw_vt_g)
    vt_is_act = (active_slot_str in ["254", "255"])
    vt_act_mark = (" ⚡ <i>[У соплі]</i>" if not is_en else " ⚡ <i>[In nozzle]</i>") if vt_is_act else ""

    if not vt_type:
        f_type = getattr(target_printer, "filament_type", "")
        if f_type and f_type not in ["Невизначено", "None", "", "Порожньо", "Empty"]:
            vt_type = f_type

    vt_has = (not vt_empty) or bool(vt_type) or vt_grams > 0 or vt_is_act
    if vt_has:
        vt_c_emoji = get_color_emoji(vt_color) if vt_color else "🧵"
        vt_clean_c = str(vt_color)[:6]
        if vt_clean_c and not vt_clean_c.startswith("#"):
            vt_clean_c = f"#{vt_clean_c}"
        vt_c_name = get_color_display_name(vt_clean_c or vt_color, lang=u_lang)
        vt_mat_full = f"{vt_type} {vt_sub}".strip() if (vt_sub and vt_sub.lower() not in vt_type.lower()) else vt_type
        if not vt_mat_full:
            vt_mat_full = "External Spool" if is_en else "Зовнішній філамент"
        vt_bar = format_progress_bar(vt_rem, vt_grams)
        ams_txt += (
            f"🧵 <b>Слот VT (Зовнішній):</b> <b>{html.escape(vt_mat_full)}</b>{vt_act_mark}\n"
            f"   🎨 Колір: <b>{vt_c_name}</b>\n"
            f"   📊 Залишок: {vt_bar}\n\n"
        ) if not is_en else (
            f"🧵 <b>Slot VT (External):</b> <b>{html.escape(vt_mat_full)}</b>{vt_act_mark}\n"
            f"   🎨 Color: <b>{vt_c_name}</b>\n"
            f"   📊 Remaining: {vt_bar}\n\n"
        )
    elif not has_ams:
        ams_txt += (
            f"⚪ <b>Слот VT (Зовнішній):</b> <i>{'Empty' if is_en else 'Порожньо'}</i>{vt_act_mark}\n\n"
        )

    if not has_ams:
        ams_txt += (
            "ℹ️ <i>Модуль AMS не підключено (використовується зовнішній котушкотримач).</i>\n"
            if not is_en
            else "ℹ️ <i>AMS module is not connected (using external spool holder).</i>\n"
        )

    await message.answer(ams_txt, parse_mode=ParseMode.HTML)

