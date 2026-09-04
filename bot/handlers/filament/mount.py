"""
Filament mounting and unmounting handlers.
"""

import html
import uuid
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_ams_slots_keyboard,
    get_main_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
    get_single_printer_filament_keyboard,
    get_spools_keyboard,
)

router = Router()


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


def get_mounted_spools_or_trays(app, spools: dict[str, Any]) -> list[dict[str, Any]]:
    mounted = []
    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}

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
                    "remaining_grams": m["remaining_grams"],
                    "price_per_kg": p_price,
                    "assigned_printer_id": None,
                    "assigned_slot_key": None,
                    "quantity": 1,
                }
            await app.storage.save_spools(spools)

            target_printer.set_slot_grams(0.0, slot_id=slot_k)
            await app.save_printers_config()

            user["state"] = "printer_menu"
            await app.storage.save_user(user)

            await message.answer(
                f"✅ <b>Котушку з {html.escape(target_printer.name)} [{m['slot_label']}] успішно знято та повернуто на Склад!</b>"
                if u_lang != "en"
                else f"✅ <b>Spool from {html.escape(target_printer.name)} [{m['slot_label']}] successfully unmounted to stock!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
            return

    if not mounted_list:
        await message.answer(
            "⚠️ Наразі жодної котушки не встановлено на принтери."
            if u_lang != "en"
            else "⚠️ No spools are currently mounted on any printer."
        )
        return

    user["state"] = "select_spool_to_unmount"
    await app.storage.save_user(user)

    buttons = [[KeyboardButton(text=m["button_text"])] for m in mounted_list]
    buttons.append([KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")])

    await message.answer(
        "🔓 <b>Оберіть котушку для зняття з принтера:</b>"
        if u_lang != "en"
        else "🔓 <b>Select spool to unmount from printer:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True),
    )
