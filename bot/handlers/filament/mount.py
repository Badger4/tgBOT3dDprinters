"""
Filament mounting and unmounting handlers.
"""

import html
import uuid
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
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
    clean = text.lower().strip()
    if any(x in clean for x in ["a1", "slot 1", "слот 1", "слот a1"]) or clean == "1":
        return "0"
    elif any(x in clean for x in ["a2", "slot 2", "слот 2", "слот a2"]) or clean == "2":
        return "1"
    elif any(x in clean for x in ["a3", "slot 3", "слот 3", "слот a3"]) or clean == "3":
        return "2"
    elif any(x in clean for x in ["a4", "slot 4", "слот 4", "слот a4"]) or clean == "4":
        return "3"
    elif any(x in clean for x in ["зовнішн", "vt", "external", "котушкотримач"]):
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

            if slot_g > 0:
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
            slot_k = m["slot_key"]
            from bot.handlers.filament.add import unassign_spool_from_slot
            res_desc, returned_to_batch = unassign_spool_from_slot(spools, m, target_printer, slot_k)
            await app.storage.save_spools(spools)

            target_printer.set_slot_grams(0.0, slot_id=slot_k)
            await app.save_printers_config()

            user["state"] = "printer_menu"
            await app.storage.save_user(user)

            await message.answer(
                f"✅ <b>Котушку з {html.escape(target_printer.name)} [{m['slot_label']}] успішно знято: {res_desc}!</b>"
                if u_lang != "en"
                else f"✅ <b>Spool from {html.escape(target_printer.name)} [{m['slot_label']}] successfully unmounted: {res_desc}!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
            hw_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Так, вивантажити" if u_lang != "en" else "✅ Yes, Unload", callback_data=f"hw_unload:{target_printer.id}:{slot_k}"),
                    InlineKeyboardButton(text="❌ Ні, пропустити" if u_lang != "en" else "❌ No, Skip", callback_data="hw_skip"),
                ]
            ])
            await message.answer(
                "❓ <b>Чи запустити функцію Unload Filament на принтері?</b>"
                if u_lang != "en"
                else "❓ <b>Execute physical Unload Filament on printer?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=hw_kb,
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


# ==========================================
# Hardware Load/Unload & Auto Sync Callbacks
# ==========================================

@router.callback_query(F.data.startswith("hw_unload:"))
async def handle_hw_unload_callback(call: CallbackQuery, app):
    chat_id = str(call.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2] if len(parts) > 2 else "254"
    printer = app.printers.get(p_id)

    if not printer:
        await call.answer("⚠️ Принтер не знайдено!" if u_lang != "en" else "⚠️ Printer not found!", show_alert=True)
        return

    if getattr(printer, "is_printing", False) or printer.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
        await call.answer(
            "⚠️ Неможливо вивантажити: принтер зараз виконує друк!"
            if u_lang != "en" else
            "⚠️ Cannot unload: printer is currently printing!",
            show_alert=True,
        )
        return

    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT (Зовнішній)"}
    slot_label = slot_names.get(str(slot_id), f"Слот {slot_id}")

    success = printer.unload_filament(slot_id=slot_id)
    if success:
        await call.answer("Команду Unload надіслано!" if u_lang != "en" else "Unload command sent!")
        await call.message.edit_text(
            f"🔄 <b>На принтер {html.escape(printer.name)} [{slot_label}] надіслано команду Unload Filament!</b>\n"
            f"Принтер обріже нитку та почне вивантаження.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await call.answer("❌ Помилка відправки команди (перевірте зв'язок з принтером)!", show_alert=True)


@router.callback_query(F.data.startswith("hw_load:"))
async def handle_hw_load_callback(call: CallbackQuery, app):
    chat_id = str(call.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2] if len(parts) > 2 else "254"
    printer = app.printers.get(p_id)

    if not printer:
        await call.answer("⚠️ Принтер не знайдено!" if u_lang != "en" else "⚠️ Printer not found!", show_alert=True)
        return

    if getattr(printer, "is_printing", False) or printer.gcode_state in ["RUNNING", "PAUSE", "PREPARE"]:
        await call.answer(
            "⚠️ Неможливо завантажити: принтер зараз виконує друк!"
            if u_lang != "en" else
            "⚠️ Cannot load: printer is currently printing!",
            show_alert=True,
        )
        return

    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT (Зовнішній)"}
    slot_label = slot_names.get(str(slot_id), f"Слот {slot_id}")

    success = printer.load_filament(slot_id=slot_id)
    if success:
        await call.answer("Команду Load надіслано!" if u_lang != "en" else "Load command sent!")
        await call.message.edit_text(
            f"🔄 <b>На принтер {html.escape(printer.name)} [{slot_label}] надіслано команду Load Filament!</b>\n"
            f"Принтер нагріє сопло та розпочне подачу нитки.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await call.answer("❌ Помилка відправки команди (перевірте зв'язок з принтером)!", show_alert=True)


@router.callback_query(F.data == "hw_skip")
async def handle_hw_skip_callback(call: CallbackQuery):
    await call.message.delete_reply_markup()
    await call.answer("Дію пропущено")


@router.callback_query(F.data.startswith("fil_auto_mount:"))
async def handle_fil_auto_mount_callback(call: CallbackQuery, app):
    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2]
    fil_type = parts[3] if len(parts) > 3 else ""
    target_p = app.printers.get(p_id)
    if not target_p:
        await call.answer("Принтер не знайдено", show_alert=True)
        return

    spools = await app.storage.load_spools()
    avail = [s for s in spools.values() if not s.get("assigned_printer_id") and int(s.get("quantity", 1)) > 0]
    if not avail:
        await call.answer("На Складі немає вільних котушок", show_alert=True)
        return

    # Sort matching type first
    if fil_type:
        avail.sort(key=lambda s: 0 if str(s.get("type", "")).upper() == fil_type.upper() else 1)

    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}
    s_label = slot_names.get(str(slot_id), f"Слот {slot_id}")

    buttons = []
    for s in avail[:8]:
        s_name = s.get("name", "Spool")
        s_mat = s.get("type", "PLA")
        s_grams = s.get("remaining_grams", 1000.0)
        btn_txt = f"🧵 {s_name} ({s_mat}, {s_grams}g)"
        buttons.append([InlineKeyboardButton(text=btn_txt, callback_data=f"fil_pick:{p_id}:{slot_id}:{s['id']}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Скасувати", callback_data=f"fil_auto_skip:{p_id}:{slot_id}")])

    await call.message.edit_text(
        f"📦 <b>Оберіть котушку зі Складу для слоту {s_label} на {html.escape(target_p.name)}:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@router.callback_query(F.data.startswith("fil_pick:"))
async def handle_fil_pick_callback(call: CallbackQuery, app):
    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2]
    spool_id = parts[3]
    target_p = app.printers.get(p_id)
    if not target_p:
        await call.answer("Принтер не знайдено", show_alert=True)
        return

    spools = await app.storage.load_spools()
    spool = spools.get(spool_id)
    if not spool:
        await call.answer("Котушку не знайдено на складі", show_alert=True)
        return

    from bot.handlers.filament.add import assign_spool_to_slot
    mounted, rem_qty = assign_spool_to_slot(spools, spool, target_p, slot_id)
    await app.storage.save_spools(spools)
    await app.save_printers_config()

    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT (Зовнішній)"}
    slot_label = slot_names.get(str(slot_id), f"Слот {slot_id}")

    rem_txt = f"\n📦 Залишок на складі: {rem_qty} шт." if rem_qty > 0 else ""
    await call.message.edit_text(
        f"✅ <b>Котушку {html.escape(mounted['name'])} успішно прив'язано до {html.escape(target_p.name)} [{slot_label}]!</b>{rem_txt}",
        parse_mode=ParseMode.HTML,
    )
    await call.answer("Котушку встановлено!")


@router.callback_query(F.data.startswith("fil_auto_add:"))
async def handle_fil_auto_add_callback(call: CallbackQuery, app):
    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2]
    fil_type = parts[3] if len(parts) > 3 else "PLA"
    chat_id = str(call.message.chat.id)
    user = await app.storage.load_user(chat_id)

    user["state"] = "add_spool_name"
    user["context_data"] = {
        "target_printer_id": p_id,
        "target_slot_key": slot_id,
        "auto_mount_on_create": True,
        "prefill_type": fil_type,
    }
    await app.storage.save_user(user)

    slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}
    s_label = slot_names.get(str(slot_id), f"Слот {slot_id}")

    await call.message.edit_text(
        f"➕ <b>Створення нової котушки ({fil_type}) для {s_label}:</b>\n\n"
        f"Введіть назву або виробника котушки (наприклад: <code>Bambu Lab Basic</code> або <code>Devil Design</code>):",
        parse_mode=ParseMode.HTML,
    )
    await call.answer()


@router.callback_query(F.data.startswith("fil_auto_skip"))
async def handle_fil_auto_skip_callback(call: CallbackQuery):
    await call.message.edit_text("✖ <b>Прив'язку котушки пропущено.</b>", parse_mode=ParseMode.HTML)
    await call.answer("Пропущено")
