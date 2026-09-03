"""
Filament and spool management (AMS slots, warehouse spools, manual weight/price edits).
"""

import html
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import (
    get_ams_slots_keyboard,
    get_filament_menu_keyboard,
    get_main_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
    get_single_printer_filament_keyboard,
    get_spool_presets_inline_keyboard,
    get_spools_keyboard,
)
from utils.math_eval import safe_eval_math

router = Router()


def extract_filament_type_from_name(name: str) -> str:
    from utils.filament_utils import extract_filament_type_from_name as _extract
    return _extract(name)


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
    elif "зовнішн" in clean or "vt" in clean or "external" in clean:
        return "254"
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

    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid and hasattr(app, "printers") else None
    msg_low = message.text.strip().lower() if message.text else ""
    is_printer_filament_btn = msg_low in ["🧵 філамент", "філамент", "🧵 filament", "filament"]

    if target_printer and is_printer_filament_btn:
        txt = (
            f"<b>🧵 Філамент & AMS — {html.escape(target_printer.name)}</b>\n\n"
            f"📦 <b>Залишок нитки на бабіні:</b> <code>{target_printer.filament_grams}g</code>\n"
            f"🎨 <b>Тип пластику:</b> <code>{target_printer.filament_type}</code>\n\n"
        ) if u_lang != "en" else (
            f"<b>🧵 Filament & AMS — {html.escape(target_printer.name)}</b>\n\n"
            f"📦 <b>Spool Remaining:</b> <code>{target_printer.filament_grams}g</code>\n"
            f"🎨 <b>Filament Type:</b> <code>{target_printer.filament_type}</code>\n\n"
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

            is_act = (str(k) == str(active_key) or (k == "254" and str(active_key) in ["254", "255"])) and has_filament
            act_str = (" ⚡ [АКТИВНИЙ]" if u_lang != "en" else " ⚡ [ACTIVE]") if is_act else ""

            if has_filament:
                pct = min(100, max(0, int((raw_g / 1000.0) * 100)))
                txt += f"   • <b>{s_name}</b>: {sp_title} — <b>{raw_g}g</b> ({pct}%){act_str}\n"
            else:
                empty_label = "Порожньо" if u_lang != "en" else "Empty"
                txt += f"   • <b>{s_name}</b>: {empty_label}\n"

        await message.answer(txt, parse_mode=ParseMode.HTML, reply_markup=get_single_printer_filament_keyboard(lang=u_lang))
        return

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
    unassigned_spools = [s for s in spool_list if not s.get("assigned_printer_id")]
    txt += (
        f"-----------------------------------\n"
        f"{sp_stock_lbl} {len(unassigned_spools)} pcs.\n"
    )

    if unassigned_spools:
        txt += ("<b>Котушки на складі:</b>\n" if u_lang != "en" else "<b>Spools in Stock:</b>\n")
        for s in unassigned_spools[-5:]:
            s_n = html.escape(s.get("name", "Spool" if u_lang == "en" else "Котушка"))
            s_t = html.escape(s.get("type", "PLA"))
            s_g = s.get("remaining_grams", 1000.0)
            s_pr = s.get("price_per_kg") or s.get("price_uah", 0.0)
            cur_str = "грн/кг" if u_lang != "en" else "UAH/kg"
            txt += f"• <b>{s_n}</b> ({s_t}) — <b>{s_g}g</b> | {s_pr} {cur_str}\n"
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

    for p in app.printers.values():
        trays = getattr(p, "ams_trays_info", {}) or {}
        for slot_id, t_info in trays.items():
            if not isinstance(t_info, dict) or t_info.get("empty", True):
                continue

            tag_uid = str(t_info.get("tag_uid") or "").strip()
            # Ignore empty, placeholder all-zeros, or non-RFID tag UIDs
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


@router.message(F.text.lower().in_(["🔗 монтаж / зняття", "монтаж / зняття", "🔗 mount / unmount", "mount / unmount"]))
async def handle_mount_unmount_choice(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔗 Встановити на принтер" if u_lang != "en" else "🔗 Mount to Printer"),
                KeyboardButton(text="🔓 Зняти з принтера" if u_lang != "en" else "🔓 Unmount from Printer"),
            ],
            [KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "⚙️ <b>Оберіть операцію з котушкою:</b>\n\n"
        "• <b>🔗 Встановити на принтер:</b> обрати вільну котушку зі Складу та призначити на слот принтера.\n"
        "• <b>🔓 Зняти з принтера:</b> зняти котушку з принтера та повернути її на Склад."
        if u_lang != "en"
        else "⚙️ <b>Select spool operation:</b>\n\n"
        "• <b>🔗 Mount to Printer:</b> choose a free spool from stock and mount to a printer slot.\n"
        "• <b>🔓 Unmount from Printer:</b> unmount a spool from a printer back to stock.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(F.text.lower().in_(["🔗 встановити на принтер", "встановити на принтер", "🔗 mount to printer", "mount to printer", "🔗 поставити котушку", "поставити котушку", "🔗 mount spool", "mount spool", "🔗 встановити", "встановити", "🔗 mount", "mount"]))
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


def get_mounted_spools_or_trays(app, spools: dict[str, Any]) -> list[dict[str, Any]]:
    mounted = []
    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}

    # 1. Spools explicitly assigned in database
    for s in spools.values():
        p_id = s.get("assigned_printer_id")
        slot_k = str(s.get("assigned_slot_key", "254"))
        if p_id and p_id in app.printers:
            p = app.printers[p_id]
            s_label = slot_names.get(slot_k, f"Слот {slot_k}")
            try:
                raw_val = s.get("remaining_grams")
                if raw_val is None:
                    raw_val = p.get_slot_grams(slot_k)
                rem_g = float(raw_val)
            except (ValueError, TypeError):
                rem_g = 1000.0
            mat = s.get("type", "PLA")
            mounted.append({
                "type_source": "db_spool",
                "spool_id": s["id"],
                "printer_id": p.id,
                "printer_name": p.name,
                "slot_key": slot_k,
                "slot_label": s_label,
                "name": s.get("name", "Spool"),
                "material": mat,
                "remaining_grams": rem_g,
                "button_text": f"🧵 {p.name} — {s_label} ({mat}, {rem_g}g)",
            })

    # 2. Also check printer slots with filament/trays that aren't already covered by a db_spool
    for p in app.printers.values():
        p_has_ams = bool(getattr(p, "has_ams", False))
        slot_keys = ["0", "1", "2", "3", "254"] if p_has_ams else ["254"]
        trays_info = getattr(p, "ams_trays_info", {}) or {}
        for k in slot_keys:
            if any(m["printer_id"] == p.id and str(m["slot_key"]) == str(k) for m in mounted):
                continue

            tray_info = trays_info.get(str(k), {}) if isinstance(trays_info, dict) else {}
            is_empty = tray_info.get("empty", True) if tray_info else True
            tray_type = str(tray_info.get("type") or "").strip()
            try:
                slot_g = float(p.get_slot_grams(k))
            except (ValueError, TypeError, AttributeError):
                slot_g = 0.0

            if (not is_empty and tray_type) or slot_g > 0:
                s_label = slot_names.get(str(k), f"Слот {k}")
                t_sub = str(tray_info.get("sub_brands") or "").strip()
                mat_type = tray_type.upper() if tray_type else getattr(p, "filament_type", "PLA")
                sp_name = f"Bambu {mat_type} {t_sub}".strip() if tray_type else f"{p.name} {s_label} Spool"

                mounted.append({
                    "type_source": "printer_slot",
                    "spool_id": None,
                    "printer_id": p.id,
                    "printer_name": p.name,
                    "slot_key": str(k),
                    "slot_label": s_label,
                    "name": sp_name,
                    "material": mat_type,
                    "remaining_grams": float(slot_g),
                    "button_text": f"🧵 {p.name} — {s_label} ({mat_type}, {slot_g}g)",
                })

    return mounted


@router.message(F.text.lower().in_(["🔓 зняти з принтера", "зняти з принтера", "🔓 unmount from printer", "unmount from printer", "🔓 unmount spool", "unmount spool", "🔓 зняти котушку", "зняти котушку", "🔓 зняти", "зняти", "🔓 unmount", "unmount"]))
async def handle_unmount_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    mounted_list = get_mounted_spools_or_trays(app, spools)

    if target_printer:
        mounted_list = [m for m in mounted_list if m["printer_id"] == target_printer.id]
        if not mounted_list:
            await message.answer(
                f"⚠️ На принтері <b>{html.escape(target_printer.name)}</b> наразі немає встановлених котушок."
                if u_lang != "en"
                else f"⚠️ No spools currently mounted on <b>{html.escape(target_printer.name)}</b>.",
                parse_mode=ParseMode.HTML,
            )
            return

        # If exactly 1 spool/tray is mounted on this printer, unmount it directly without asking
        if len(mounted_list) == 1:
            m = mounted_list[0]
            p_id = m["printer_id"]
            slot_k = m["slot_key"]
            if m["type_source"] == "db_spool" and m.get("spool_id"):
                target_spool = spools.get(m["spool_id"])
                if target_spool:
                    target_spool["assigned_printer_id"] = None
                    target_spool["assigned_slot_key"] = None
                    target_spool["remaining_grams"] = m["remaining_grams"]
                    spools[target_spool["id"]] = target_spool
            else:
                new_id = f"spool_{str(uuid.uuid4())[:8]}"
                p_price = float(getattr(target_printer, "price_per_kg", 850.0) or 850.0)
                spools[new_id] = {
                    "id": new_id,
                    "name": m["name"],
                    "type": m["material"],
                    "color": "#000000",
                    "remaining_grams": m["remaining_grams"],
                    "price_per_kg": p_price,
                    "price_uah": p_price,
                    "assigned_printer_id": None,
                    "assigned_slot_key": None,
                    "quantity": 1,
                }
            await app.storage.save_spools(spools)
            target_printer.set_slot_grams(0.0, slot_id=str(slot_k))
            await app.save_printers_config()

            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"🔓 <b>Котушку «{html.escape(m['name'])}» ({m['remaining_grams']}g) успішно знято з {html.escape(target_printer.name)} [{m['slot_label']}] та збережено на Складі!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
            return

    if not mounted_list:
        await message.answer("⚠️ Наразі жодної котушки не встановлено на принтери." if u_lang != "en" else "⚠️ No spools currently mounted on printers.")
        return

    user["state"] = "select_spool_to_unmount"
    await app.storage.save_user(user)

    keyboard = []
    for m in mounted_list:
        if target_printer:
            btn_txt = f"🧵 {m['slot_label']} — {m['name']} ({m['material']}, {m['remaining_grams']}g)"
            m["button_text"] = btn_txt
            keyboard.append([KeyboardButton(text=btn_txt)])
        else:
            keyboard.append([KeyboardButton(text=m["button_text"])])
    keyboard.append([KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")])
    kb = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    prompt_txt = (
        f"🔓 <b>Оберіть котушку для зняття з {html.escape(target_printer.name)} на Склад:</b>"
        if target_printer
        else "🔓 <b>Оберіть котушку для зняття з принтера на Склад:</b>"
    ) if u_lang != "en" else (
        f"🔓 <b>Select spool to unmount from {html.escape(target_printer.name)} back to stock:</b>"
        if target_printer
        else "🔓 <b>Select spool to unmount back to stock:</b>"
    )

    await message.answer(
        prompt_txt,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
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
                slot_num = 1

            active_mark = " ⚡" if t.get("is_active") else ""
            if t_rem >= 0:
                rem_str = f"{t_rem}%"
            else:
                rem_str = f"~{target_printer.filament_grams}g"

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
            "✏️ manual weight input", "manual weight input", "✏️ змінити вагу", "змінити вагу", "✏️ edit weight", "edit weight"
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


@router.message(F.text.lower().in_(["✏️ редагувати котушку", "редагувати котушку", "✏️ редагувати", "редагувати", "✏️ edit spool", "edit spool"]))
async def handle_edit_spool_start(message: Message, state: FSMContext, app: Any):
    curr_state = await state.get_state()
    if curr_state and "Part" in str(curr_state):
        return

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


@router.message(F.text.lower().in_(["🗑️ видалити котушку", "видалити котушку", "🗑️ видалити", "видалити", "🗑️ delete spool", "delete spool"]))
async def handle_delete_spool_start(message: Message, state: FSMContext, app: Any):
    curr_state = await state.get_state()
    if curr_state and "Part" in str(curr_state):
        return

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


@router.message(F.text.lower().in_(["➕ нова котушка", "нова котушка", "➕ додати", "додати", "➕ додати котушку", "додати котушку", "➕ new spool", "new spool", "➕ add spool", "add spool"]))
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
    "add_spool_type",
    "add_spool_grams",
    "add_spool_price",
    "select_spool_to_edit",
    "select_spool_field",
    "edit_spool_name",
    "edit_spool_type",
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
    u_lang = user.get("language", "uk")
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
            selected_pid = user.get("context_data", {}).get("selected_printer_id")
            target_p = app.printers.get(selected_pid) if selected_pid else None

            if target_p:
                user["context_data"]["mount_printer_id"] = target_p.id
                if getattr(target_p, "has_ams", False):
                    user["state"] = "select_slot_for_mount"
                    await app.storage.save_user(user)
                    await message.answer(
                        f"📍 <b>Оберіть слот AMS для {html.escape(target_p.name)}:</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_ams_slots_keyboard(target_p),
                    )
                else:
                    slot_key = "254"
                    # Unassign previous spool from this slot
                    for s_id, s in list(spools.items()):
                        if s.get("assigned_printer_id") == target_p.id and str(s.get("assigned_slot_key")) == slot_key:
                            s["assigned_printer_id"] = None
                            s["assigned_slot_key"] = None
                            spools[s_id] = s

                    target_spool = spools.get(selected["id"])
                    if target_spool:
                        target_spool["assigned_printer_id"] = target_p.id
                        target_spool["assigned_slot_key"] = slot_key
                        spools[selected["id"]] = target_spool
                        await app.storage.save_spools(spools)

                    grams = float(selected.get("remaining_grams", 1000.0))
                    target_p.set_slot_grams(grams, slot_id=slot_key)
                    if selected.get("type"):
                        target_p.filament_type = str(selected.get("type"))
                    await app.save_printers_config()

                    user["state"] = "printer_menu"
                    user["context_data"].pop("mount_spool", None)
                    user["context_data"].pop("mount_printer_id", None)
                    await app.storage.save_user(user)

                    await message.answer(
                        f"✅ <b>Котушку {html.escape(selected['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
                    )
            else:
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

            selected_pid = user.get("context_data", {}).get("selected_printer_id")
            if selected_pid and selected_pid == target_p.id:
                user["state"] = "printer_menu"
                kb = get_single_printer_filament_keyboard(lang=u_lang)
            else:
                user["state"] = "idle"
                kb = get_filament_menu_keyboard(lang=u_lang)

            user["context_data"].pop("mount_spool", None)
            user["context_data"].pop("mount_printer_id", None)
            await app.storage.save_user(user)

            await message.answer(
                f"✅ <b>Котушку {html.escape(selected_spool['name'])} встановлено на {html.escape(target_p.name)} [Слот {slot_label}]!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        return True

    if state == "select_spool_to_unmount":
        spools = await app.storage.load_spools()
        mounted_list = get_mounted_spools_or_trays(app, spools)
        selected_pid = user.get("context_data", {}).get("selected_printer_id")
        if selected_pid and selected_pid in app.printers:
            mounted_list = [m for m in mounted_list if m["printer_id"] == selected_pid]

        selected = None
        for m in mounted_list:
            b_txt = m["button_text"]
            m_name = m["name"]
            p_name = m["printer_name"]
            s_lbl = m["slot_label"]
            if (
                text == b_txt
                or m_name in text
                or (s_lbl in text and (p_name in text or selected_pid))
                or text in [f"🧵 {s_lbl}", s_lbl]
            ):
                selected = m
                break

        if selected:
            p_id = selected["printer_id"]
            slot_k = selected["slot_key"]
            if selected["type_source"] == "db_spool" and selected.get("spool_id"):
                target_spool = spools.get(selected["spool_id"])
                if target_spool:
                    target_spool["assigned_printer_id"] = None
                    target_spool["assigned_slot_key"] = None
                    target_spool["remaining_grams"] = selected["remaining_grams"]
                    spools[target_spool["id"]] = target_spool
            else:
                new_id = f"spool_{str(uuid.uuid4())[:8]}"
                p_price = 850.0
                if p_id and p_id in app.printers:
                    p_price = float(getattr(app.printers[p_id], "price_per_kg", 850.0) or 850.0)
                spools[new_id] = {
                    "id": new_id,
                    "name": selected["name"],
                    "type": selected["material"],
                    "color": "#000000",
                    "remaining_grams": selected["remaining_grams"],
                    "price_per_kg": p_price,
                    "price_uah": p_price,
                    "assigned_printer_id": None,
                    "assigned_slot_key": None,
                    "quantity": 1,
                }

            await app.storage.save_spools(spools)

            if p_id and p_id in app.printers:
                p = app.printers[p_id]
                p.set_slot_grams(0.0, slot_id=str(slot_k))
                await app.save_printers_config()

            if selected_pid and selected_pid == p_id:
                user["state"] = "printer_menu"
                kb = get_single_printer_filament_keyboard(lang=u_lang)
            else:
                user["state"] = "idle"
                kb = get_filament_menu_keyboard(lang=u_lang)

            await app.storage.save_user(user)
            await message.answer(
                f"🔓 <b>Котушку «{html.escape(selected['name'])}» ({selected['remaining_grams']}g) успішно знято з {html.escape(selected['printer_name'])} [{selected['slot_label']}] та збережено на Складі!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
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
                final_val = max(0.0, deducted_val)
                target_printer.set_slot_grams(final_val, slot_key)
                target_printer._job_deducted = True
                msg_note = f" (враховано поточний друк {target_printer._current_job_grams}g ➔ {final_val}g)"
            else:
                final_val = max(0.0, val)
                target_printer.set_slot_grams(final_val, slot_key)
                msg_note = ""

            # If weight is 0, auto-delete any database spool assigned to this slot
            spools = await app.storage.load_spools()
            deleted_s = None
            if final_val <= 0.0:
                for s_id, s in list(spools.items()):
                    if s.get("assigned_printer_id") == target_printer.id and str(s.get("assigned_slot_key")) == slot_key:
                        deleted_s = s
                        del spools[s_id]
                if deleted_s:
                    await app.storage.save_spools(spools)

            await app.save_printers_config()
            user["state"] = "printer_menu"
            user["context_data"].pop("pending_weight", None)
            await app.storage.save_user(user)

            if final_val <= 0.0:
                del_note = f"\n🗑️ Котушку «{html.escape(deleted_s['name'])}» автоматично видалено зі Складу." if deleted_s else ""
                await message.answer(
                    f"✅ <b>Залишок для Слоту {slot_label} оновлено: 0.0g (Порожньо)</b>!{del_note}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
                )
            else:
                await message.answer(
                    f"✅ **Залишок для Слоту {slot_label} оновлено: {target_printer.get_slot_grams(slot_key)}g**{msg_note}!",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
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
        user["context_data"]["new_spool"]["name"] = text.strip()
        user["state"] = "add_spool_type"
        await app.storage.save_user(user)
        type_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="PLA"), KeyboardButton(text="PETG"), KeyboardButton(text="ABS")],
                [KeyboardButton(text="ASA"), KeyboardButton(text="TPU"), KeyboardButton(text="PC")],
                [KeyboardButton(text="PA-CF"), KeyboardButton(text="PETG-CF"), KeyboardButton(text="PLA-CF")],
                [KeyboardButton(text="⬅️ Назад")],
            ],
            resize_keyboard=True,
        )
        await message.answer(
            f"🧵 <b>Оберіть або введіть тип пластику</b> для котушки «{html.escape(text.strip())}»:\n"
            f"<i>(Наприклад: PLA, PETG, ABS, TPU, ASA, PC або введіть свій)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=type_kb,
        )
        return True

    if state == "add_spool_type":
        user["context_data"]["new_spool"]["type"] = text.strip().upper()
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)
        await message.answer(
            "⚖️ Введіть початкову/залишкову вагу котушки в грамах (наприклад <code>1000</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
        )
        return True

    if state == "add_spool_grams":
        val = safe_eval_math(text) or 1000.0
        user["context_data"]["new_spool"]["remaining_grams"] = val
        user["context_data"]["new_spool"]["total_grams"] = val
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)
        await message.answer(
            "💰 Введіть ціну за 1 кг у грн (наприклад <code>650</code> або <code>850</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
        )
        return True

    if state == "add_spool_price":
        price_val = safe_eval_math(text) or 650.0
        new_s = user["context_data"].get("new_spool", {})
        spool_id = f"spool_{str(uuid.uuid4())[:8]}"
        new_s["id"] = spool_id
        new_s["price_uah"] = price_val
        new_s["price_per_kg"] = price_val
        if not new_s.get("type"):
            new_s["type"] = "PLA"
        new_s["color"] = "Standart"

        spools = await app.storage.load_spools()
        spools[spool_id] = new_s
        await app.storage.save_spools(spools)

        user["state"] = "printer_menu" if target_printer else "idle"
        user["context_data"].pop("new_spool", None)
        await app.storage.save_user(user)
        kb = (
            get_printer_menu_keyboard(target_printer)
            if target_printer
            else get_filament_menu_keyboard(lang=u_lang)
        )
        await message.answer(
            f"✅ Нову котушку <b>{html.escape(new_s['name'])}</b> (Тип: <b>{html.escape(new_s['type'])}</b>, {new_s['remaining_grams']}g, {price_val} грн/кг) додано на склад!",
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
                    [KeyboardButton(text="📝 Назву"), KeyboardButton(text="🧵 Тип пластику")],
                    [KeyboardButton(text="⚖️ Залишкову вагу (g)"), KeyboardButton(text="💰 Вартість 1 кг (грн)")],
                    [KeyboardButton(text="⬅️ Назад")],
                ],
                resize_keyboard=True,
            )
            await message.answer(
                f"📝 <b>Оберіть параметр для редагування котушки {html.escape(selected_spool['name'])}:</b>\n"
                f"• Тип: <b>{selected_spool.get('type', 'PLA')}</b>\n"
                f"• Поточний залишок: {selected_spool.get('remaining_grams', 1000.0)}g\n"
                f"• Поточна ціна: {selected_spool.get('price_uah', 650.0)} грн/кг",
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

        if text in ["📝 Назву", "📝 Назву / Тип"]:
            user["state"] = "edit_spool_name"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть нову назву для котушки <b>{html.escape(spool['name'])}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
            )
        elif text in ["🧵 Тип пластику", "Тип пластику", "Тип"]:
            user["state"] = "edit_spool_type"
            await app.storage.save_user(user)
            type_kb = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="PLA"), KeyboardButton(text="PETG"), KeyboardButton(text="ABS")],
                    [KeyboardButton(text="ASA"), KeyboardButton(text="TPU"), KeyboardButton(text="PC")],
                    [KeyboardButton(text="PA-CF"), KeyboardButton(text="PETG-CF"), KeyboardButton(text="PLA-CF")],
                    [KeyboardButton(text="⬅️ Назад")],
                ],
                resize_keyboard=True,
            )
            await message.answer(
                f"🧵 <b>Оберіть або введіть новий тип пластику</b> для котушки <b>{html.escape(spool['name'])}</b> (поточний: {spool.get('type', 'PLA')}):",
                parse_mode=ParseMode.HTML,
                reply_markup=type_kb,
            )
        elif text == "⚖️ Залишкову вагу (g)":
            user["state"] = "edit_spool_grams"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть новий залишок ваги (в грамах) для <b>{html.escape(spool['name'])}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад")]], resize_keyboard=True),
            )
        elif text in ["💰 Вартість 1 кг (грн)", "💰 Вартість (грн)"]:
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
                spools[s_id]["name"] = text.strip()
                await app.storage.save_spools(spools)
                user["state"] = "printer_menu" if target_printer else "idle"
                user["context_data"].pop("edit_spool", None)
                await app.storage.save_user(user)
                kb = (
                    get_printer_menu_keyboard(target_printer)
                    if target_printer
                    else get_filament_menu_keyboard(lang=u_lang)
                )
                await message.answer(
                    f"✅ Назву оновлено на: <b>{html.escape(text.strip())}</b>!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
        return True

    if state == "edit_spool_type":
        spool = ctx_data.get("edit_spool")
        if spool:
            spools = await app.storage.load_spools()
            s_id = spool["id"]
            if s_id in spools:
                new_type = text.strip().upper()
                spools[s_id]["type"] = new_type
                await app.storage.save_spools(spools)
                user["state"] = "printer_menu" if target_printer else "idle"
                user["context_data"].pop("edit_spool", None)
                await app.storage.save_user(user)
                kb = (
                    get_printer_menu_keyboard(target_printer)
                    if target_printer
                    else get_filament_menu_keyboard(lang=u_lang)
                )
                await message.answer(
                    f"✅ Тип пластику для <b>{html.escape(spools[s_id]['name'])}</b> оновлено на <b>{new_type}</b>!",
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
            user["state"] = "printer_menu" if target_printer else "idle"
            user["context_data"].pop("edit_spool", None)
            await app.storage.save_user(user)
            kb = (
                get_printer_menu_keyboard(target_printer)
                if target_printer
                else get_main_keyboard(await app.is_user_admin(chat_id))
            )
            if val <= 0:
                if s_id in spools:
                    del spools[s_id]
                    await app.storage.save_spools(spools)
                await message.answer(
                    f"🗑️ Котушку <b>{html.escape(spool['name'])}</b> автоматично видалено зі Складу, оскільки її вага дійшла до <b>0g</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            else:
                if s_id in spools:
                    spools[s_id]["remaining_grams"] = val
                    spools[s_id]["total_grams"] = max(val, float(spools[s_id].get("total_grams", 1000.0)))
                    await app.storage.save_spools(spools)
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
