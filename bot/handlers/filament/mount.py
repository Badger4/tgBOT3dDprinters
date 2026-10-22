"""
Filament mounting and unmounting handlers.
"""

import html
import logging
import uuid
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_ams_slots_keyboard,
    get_filament_menu_keyboard,
    get_main_keyboard,
    get_printer_menu_keyboard,
    get_printers_keyboard,
    get_printers_mount_keyboard,
    get_single_printer_filament_keyboard,
    get_spools_keyboard,
)
from utils.filament_utils import get_color_emoji
from utils.math_eval import safe_eval_math

logger = logging.getLogger(__name__)

router = Router()

CANCEL_KEYWORDS = {
    "відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад",
    "cancel", "/cancel", "back", "⬅️ back", "❌ скасувати", "❌ cancel",
    "головне меню", "⬅️ головне меню", "main menu", "⬅️ main menu",
    "повернутись в меню", "назад в меню", "⬅️ назад в меню",
}
STEP_BACK_KEYWORDS = {"↩️ крок назад", "крок назад", "step back", "↩️ step back"}

MOUNT_STATES = {
    "select_spool_to_mount",
    "select_printer_for_mount",
    "select_slot_for_mount",
    "select_slot_for_weight",
    "select_spool_to_unmount",
}


def unassign_spool_from_slot(spools: dict, selected_item: dict, target_p, slot_k: str) -> tuple[str, bool]:
    """
    Unmounts a spool from a printer slot.
    Checks if weight changed from initial_grams:
    - If weight NOT changed: returns to parent batch (increments quantity by 1, deletes copy).
    - If weight CHANGED: saved as a separate started spool with its new weight (quantity=1).
    Returns (result_description, returned_to_batch: bool).
    """
    spool_id = selected_item.get("spool_id")
    target_spool = spools.get(spool_id) if spool_id else None

    if not target_spool and target_p:
        for s in spools.values():
            if s.get("assigned_printer_id") == target_p.id and str(s.get("assigned_slot_key")) == str(slot_k):
                target_spool = s
                break

    rem_g = float(selected_item.get("remaining_grams", 1000.0))

    if not target_spool:
        new_id = f"spool_{str(uuid.uuid4())[:8]}"
        p_price = float(getattr(target_p, "price_per_kg", 850.0) or 850.0) if target_p else 850.0
        spools[new_id] = {
            "id": new_id,
            "name": selected_item.get("name", "Spool"),
            "type": selected_item.get("material", "PLA"),
            "color": selected_item.get("color", "#3B82F6"),
            "remaining_grams": round(rem_g, 1),
            "initial_grams": round(rem_g, 1),
            "price_per_kg": p_price,
            "assigned_printer_id": None,
            "assigned_slot_key": None,
            "quantity": 1,
        }
        return f"{rem_g}g (1 шт)", False

    init_g = float(target_spool.get("initial_grams", target_spool.get("remaining_grams", 1000.0)))
    weight_unchanged = round(rem_g, 1) >= round(init_g, 1)

    if weight_unchanged:
        parent_id = target_spool.get("parent_spool_id")
        parent_spool = spools.get(parent_id) if parent_id else None

        if not parent_spool:
            for s_id, s in spools.items():
                if (
                    not s.get("assigned_printer_id")
                    and s.get("name") == target_spool.get("name")
                    and s.get("type") == target_spool.get("type")
                    and s.get("color") == target_spool.get("color")
                    and round(float(s.get("remaining_grams", 0)), 1) == round(init_g, 1)
                ):
                    parent_spool = s
                    break

        if parent_spool and not parent_spool.get("assigned_printer_id"):
            parent_spool["quantity"] = int(parent_spool.get("quantity", 1)) + 1
            spools[parent_spool["id"]] = parent_spool
            if target_spool["id"] != parent_spool["id"] and target_spool["id"] in spools:
                del spools[target_spool["id"]]
            return f"повернуто до пачки (разом: {parent_spool['quantity']} шт)", True
        else:
            target_spool["assigned_printer_id"] = None
            target_spool["assigned_slot_key"] = None
            target_spool["remaining_grams"] = round(init_g, 1)
            target_spool["quantity"] = max(1, int(target_spool.get("quantity", 1)))
            spools[target_spool["id"]] = target_spool
            return f"повернуто на Склад ({target_spool['quantity']} шт)", True
    else:
        target_spool["assigned_printer_id"] = None
        target_spool["assigned_slot_key"] = None
        target_spool["remaining_grams"] = round(rem_g, 1)
        target_spool["quantity"] = 1
        target_spool.pop("parent_spool_id", None)
        spools[target_spool["id"]] = target_spool
        return f"розпочата котушка: {round(rem_g, 1)}g (1 шт)", False


def assign_spool_to_slot(spools: dict, src_spool: dict, target_p, slot_key: str) -> tuple[dict, int]:
    """
    Assigns a spool to a printer slot.
    If src_spool has quantity > 1, decrements warehouse batch quantity by 1,
    and creates a new mounted instance with quantity=1 and parent_spool_id.
    Returns (mounted_spool, remaining_warehouse_qty).
    """
    slot_str = str(slot_key)
    for s_id, s in list(spools.items()):
        if s.get("assigned_printer_id") == target_p.id and str(s.get("assigned_slot_key")) == slot_str and s_id != src_spool.get("id"):
            prev_grams = target_p.get_slot_grams(slot_key) if hasattr(target_p, "get_slot_grams") else s.get("remaining_grams", 1000.0)
            unassign_spool_from_slot(spools, {"spool_id": s_id, "remaining_grams": prev_grams}, target_p, slot_str)

    src_id = src_spool["id"]
    db_src = spools.get(src_id, src_spool)
    qty = max(1, int(db_src.get("quantity", 1) or 1))

    if qty > 1:
        db_src["quantity"] = qty - 1
        spools[src_id] = db_src

        new_id = f"spool_{str(uuid.uuid4())[:8]}"
        mounted = db_src.copy()
        mounted["id"] = new_id
        mounted["parent_spool_id"] = src_id
        mounted["quantity"] = 1
        mounted["assigned_printer_id"] = target_p.id
        mounted["assigned_slot_key"] = slot_str
        if "initial_grams" not in mounted:
            mounted["initial_grams"] = float(mounted.get("remaining_grams", 1000.0))
        spools[new_id] = mounted
        rem_warehouse_qty = qty - 1
        ret_spool = mounted
    else:
        db_src["assigned_printer_id"] = target_p.id
        db_src["assigned_slot_key"] = slot_str
        db_src["quantity"] = 1
        if "initial_grams" not in db_src:
            db_src["initial_grams"] = float(db_src.get("remaining_grams", 1000.0))
        spools[src_id] = db_src
        rem_warehouse_qty = 0
        ret_spool = db_src

    grams = float(ret_spool.get("remaining_grams", 1000.0))
    target_p.set_slot_grams(grams, slot_id=slot_key)
    if ret_spool.get("type"):
        target_p.filament_type = str(ret_spool.get("type"))

    return ret_spool, rem_warehouse_qty


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

            if not is_empty and slot_g > 0:
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

    text_lower = message.text.strip().lower() if message.text else ""
    printer_btn_keywords = {"🔗 поставити котушку", "поставити котушку", "🔗 mount spool", "mount spool"}
    has_target_printer = bool(user.get("context_data", {}).get("selected_printer_id"))

    if text_lower in printer_btn_keywords or has_target_printer:
        user.setdefault("context_data", {})["mount_source"] = "printer"
    else:
        user.setdefault("context_data", {})["mount_source"] = "warehouse"
        user.get("context_data", {}).pop("selected_printer_id", None)

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
    
    text_lower = message.text.strip().lower() if message.text else ""
    printer_btn_keywords = {"🔓 зняти котушку", "зняти котушку", "🔓 unmount spool", "unmount spool"}
    has_target_printer = bool(user.get("context_data", {}).get("selected_printer_id"))

    if text_lower in printer_btn_keywords or has_target_printer:
        user.setdefault("context_data", {})["unmount_source"] = "printer"
    else:
        user.setdefault("context_data", {})["unmount_source"] = "warehouse"
        user.get("context_data", {}).pop("selected_printer_id", None)

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
    try:
        success = printer.unload_filament(slot_id=slot_id)
    except Exception as e:
        logger.error(f"Error executing unload_filament on [{printer.name}]: {e}")
        success = False

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

    try:
        success = printer.load_filament(slot_id=slot_id)
    except Exception as e:
        logger.error(f"Error executing load_filament on [{printer.name}]: {e}")
        success = False

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
    target_p = app.printers.get(p_id) or next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)
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
        buttons.append([InlineKeyboardButton(text=btn_txt, callback_data=f"fil_pk:{target_p.id[:8]}:{slot_id}:{s['id'][:12]}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Скасувати", callback_data=f"fil_skip:{target_p.id[:8]}:{slot_id}")])

    await call.message.edit_text(
        f"📦 <b>Оберіть котушку зі Складу для слоту {s_label} на {html.escape(target_p.name)}:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await call.answer()


@router.callback_query(F.data.startswith("fil_pick:") | F.data.startswith("fil_pk:"))
async def handle_fil_pick_callback(call: CallbackQuery, app):
    parts = call.data.split(":")
    p_id = parts[1]
    slot_id = parts[2]
    spool_id = parts[3]
    target_p = app.printers.get(p_id) or next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)
    if not target_p:
        await call.answer("Принтер не знайдено", show_alert=True)
        return

    spools = await app.storage.load_spools()
    spool = spools.get(spool_id) or next((s for sid, s in spools.items() if sid.startswith(spool_id)), None)
    if not spool:
        await call.answer("Котушку не знайдено на складі", show_alert=True)
        return

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

    target_p = app.printers.get(p_id) or next((p for pid, p in app.printers.items() if pid.startswith(p_id)), None)
    resolved_pid = target_p.id if target_p else p_id

    user["state"] = "add_spool_name"
    user["context_data"] = {
        "target_printer_id": resolved_pid,
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


@router.callback_query(F.data.startswith("fil_auto_skip") | F.data.startswith("fil_skip"))
async def handle_fil_auto_skip_callback(call: CallbackQuery):
    await call.message.edit_text("✖ <b>Прив'язку котушки пропущено.</b>", parse_mode=ParseMode.HTML)
    await call.answer("Пропущено")


async def handle_mount_states(message: Message, app, user: dict, state: str, text: str) -> bool:
    chat_id = str(message.chat.id)
    u_lang = user.get("language", "uk")
    ctx_data = user.get("context_data", {})
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if state == "select_spool_to_mount":
        spools = await app.storage.load_spools()
        selected = None
        unassigned_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
        for s in unassigned_spools:
            s_id = s.get("id", "")
            s_name = s.get("name", "Spool")
            s_type = s.get("type", "")
            s_grams = s.get("remaining_grams", 1000.0)
            qty = max(1, int(s.get("quantity", 1) or 1))
            color_emoji = get_color_emoji(s.get("color_name") or s.get("color", ""))
            c_prefix = f"{color_emoji} " if color_emoji else ""
            type_str = f"{s_type}, " if (s_type and s_type.lower() not in s_name.lower()) else ""
            qty_unit = "pcs" if u_lang == "en" else "шт"
            qty_str = f" [📦 {qty} {qty_unit}]" if qty > 1 else ""
            qty_str_alt = f" [📦 {qty} {'шт' if qty_unit == 'pcs' else 'pcs'}]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"
            exact_title_alt = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str_alt}"

            if text in [exact_title, exact_title_alt, s_name, s_id] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in unassigned_spools:
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s.get("id") == text.strip()):
                    selected = s
                    break
        if not selected:
            for s in spools.values():
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s.get("id") == text.strip()):
                    selected = s
                    break

        if selected:
            user["context_data"]["mount_spool"] = selected
            mount_src = user.get("context_data", {}).get("mount_source")
            selected_pid = user.get("context_data", {}).get("selected_printer_id") if mount_src != "warehouse" else None
            target_p = app.printers.get(selected_pid) if selected_pid else None

            if target_p:
                user["context_data"]["mount_printer_id"] = target_p.id
                if getattr(target_p, "has_ams", False):
                    user["state"] = "select_slot_for_mount"
                    await app.storage.save_user(user)
                    await message.answer(
                        f"📍 <b>Оберіть слот AMS для {html.escape(target_p.name)}:</b>"
                        if u_lang != "en" else
                        f"📍 <b>Select AMS slot for {html.escape(target_p.name)}:</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_ams_slots_keyboard(target_p, lang=u_lang),
                    )
                else:
                    slot_key = "254"
                    mounted_spool, rem_stock = assign_spool_to_slot(spools, selected, target_p, slot_key)
                    await app.storage.save_spools(spools)
                    await app.save_printers_config()

                    is_from_warehouse = (mount_src == "warehouse" or not selected_pid)
                    if is_from_warehouse:
                        user["state"] = "idle"
                        user.get("context_data", {}).pop("selected_printer_id", None)
                        user.get("context_data", {}).pop("mount_source", None)
                        user.get("context_data", {}).pop("mount_spool", None)
                        user.get("context_data", {}).pop("mount_printer_id", None)
                        await app.storage.save_user(user)
                        menu_kb = get_filament_menu_keyboard(lang=u_lang)
                    else:
                        user["state"] = "printer_menu"
                        user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                        user.get("context_data", {}).pop("mount_spool", None)
                        user.get("context_data", {}).pop("mount_printer_id", None)
                        await app.storage.save_user(user)
                        menu_kb = get_single_printer_filament_keyboard(lang=u_lang)

                    stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
                    stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

                    await message.answer(
                        f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>{stock_info}"
                        if u_lang != "en" else
                        f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>{stock_info_en}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=menu_kb,
                    )
                    hw_kb = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Так, завантажити" if u_lang != "en" else "✅ Yes, Load", callback_data=f"hw_load:{target_p.id}:254"),
                            InlineKeyboardButton(text="❌ Ні, пропустити" if u_lang != "en" else "❌ No, Skip", callback_data="hw_skip"),
                        ]
                    ])
                    await message.answer(
                        "❓ <b>Чи запустити функцію Load Filament на принтері?</b>"
                        if u_lang != "en" else
                        "❓ <b>Execute physical Load Filament on printer?</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=hw_kb,
                    )
            else:
                user["state"] = "select_printer_for_mount"
                await app.storage.save_user(user)
                await message.answer(
                    f"🖨️ <b>Оберіть принтер для установки котушки {html.escape(selected['name'])}:</b>"
                    if u_lang != "en" else
                    f"🖨️ <b>Select printer to mount spool {html.escape(selected['name'])}:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_printers_mount_keyboard(app.printers, lang=u_lang),
                )
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    if state == "select_printer_for_mount":
        selected_spool = ctx_data.get("mount_spool")
        mount_src = ctx_data.get("mount_source")

        if text.lower() in CANCEL_KEYWORDS or text.strip().lower() in STEP_BACK_KEYWORDS:
            spools = await app.storage.load_spools()
            available_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
            user["state"] = "select_spool_to_mount"
            user.get("context_data", {}).pop("mount_printer_id", None)
            await app.storage.save_user(user)
            await message.answer(
                "🔗 <b>Оберіть котушку зі Складу для установки на принтер:</b>" if u_lang != "en" else "🔗 <b>Select spool from stock to mount:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_spools_keyboard({s["id"]: s for s in available_spools}, lang=u_lang),
            )
            return True

        target_p = None
        for p in app.printers.values():
            if text in [f"🖨️ {p.name}", p.name]:
                target_p = p
                break
        if not target_p:
            for p in app.printers.values():
                if text.strip().lower() in [f"🖨️ {p.name}".lower(), p.name.lower()]:
                    target_p = p
                    break

        if target_p and selected_spool:
            user["context_data"]["mount_printer_id"] = target_p.id
            if getattr(target_p, "has_ams", False):
                user["state"] = "select_slot_for_mount"
                await app.storage.save_user(user)
                await message.answer(
                    f"📍 <b>Оберіть слот AMS для {html.escape(target_p.name)}:</b>"
                    if u_lang != "en" else
                    f"📍 <b>Select AMS slot for {html.escape(target_p.name)}:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_ams_slots_keyboard(target_p, lang=u_lang),
                )
            else:
                slot_key = "254"
                spools = await app.storage.load_spools()
                mounted_spool, rem_stock = assign_spool_to_slot(spools, selected_spool, target_p, slot_key)
                await app.storage.save_spools(spools)
                await app.save_printers_config()

                is_from_warehouse = (mount_src == "warehouse" or not selected_pid)
                if is_from_warehouse:
                    user["state"] = "idle"
                    user.get("context_data", {}).pop("selected_printer_id", None)
                    user.get("context_data", {}).pop("mount_source", None)
                    user.get("context_data", {}).pop("mount_spool", None)
                    user.get("context_data", {}).pop("mount_printer_id", None)
                    await app.storage.save_user(user)
                    menu_kb = get_filament_menu_keyboard(lang=u_lang)
                else:
                    user["state"] = "printer_menu"
                    user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                    user.get("context_data", {}).pop("mount_spool", None)
                    user.get("context_data", {}).pop("mount_printer_id", None)
                    await app.storage.save_user(user)
                    menu_kb = get_single_printer_filament_keyboard(lang=u_lang)

                stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
                stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

                await message.answer(
                    f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>{stock_info}"
                    if u_lang != "en" else
                    f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>{stock_info_en}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=menu_kb,
                )
                hw_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Так, завантажити" if u_lang != "en" else "✅ Yes, Load", callback_data=f"hw_load:{target_p.id}:254"),
                        InlineKeyboardButton(text="❌ Ні, пропустити" if u_lang != "en" else "❌ No, Skip", callback_data="hw_skip"),
                    ]
                ])
                await message.answer(
                    "❓ <b>Чи запустити функцію Load Filament на принтері?</b>"
                    if u_lang != "en" else
                    "❓ <b>Execute physical Load Filament on printer?</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=hw_kb,
                )
        else:
            await message.answer(
                "⚠️ Оберіть принтер зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a printer from the keyboard list."
            )
        return True

    if state == "select_slot_for_mount":
        selected_spool = ctx_data.get("mount_spool")
        p_id = ctx_data.get("mount_printer_id")
        mount_src = ctx_data.get("mount_source")
        target_p = app.printers.get(p_id) if p_id else None

        if text.lower() in CANCEL_KEYWORDS or text.strip().lower() in STEP_BACK_KEYWORDS:
            if mount_src == "warehouse":
                user["state"] = "select_printer_for_mount"
                user.get("context_data", {}).pop("mount_printer_id", None)
                await app.storage.save_user(user)
                spool_name = selected_spool.get("name", "котушки") if selected_spool else "котушки"
                await message.answer(
                    f"🖨️ <b>Оберіть принтер для установки котушки {html.escape(spool_name)}:</b>"
                    if u_lang != "en" else
                    f"🖨️ <b>Select printer to mount spool {html.escape(spool_name)}:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_printers_mount_keyboard(app.printers, lang=u_lang),
                )
                return True
            else:
                user["state"] = "printer_menu"
                user.get("context_data", {}).pop("mount_spool", None)
                user.get("context_data", {}).pop("mount_printer_id", None)
                await app.storage.save_user(user)
                await message.answer(
                    "Дію скасовано." if u_lang != "en" else "Action cancelled.",
                    reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
                )
                return True

        if not target_p or not selected_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Помилка: сесію скинуто.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        clean = text.lower()
        is_valid_slot = any(k in clean for k in ["a1", "slot 1", "слот a1", "слот 1", "a2", "slot 2", "слот a2", "слот 2", "a3", "slot 3", "слот a3", "слот 3", "a4", "slot 4", "слот a4", "слот 4", "зовнішн", "vt", "external"])
        if not is_valid_slot:
            await message.answer(
                "⚠️ Невідомий слот. Оберіть слот зі списку на клавіатурі (наприклад: 📍 Слот A1 або Зовнішній):"
                if u_lang != "en" else
                "⚠️ Unknown slot. Please select a slot from the keyboard (e.g. 📍 Slot A1 or External):"
            )
            return True

        slot_key = parse_slot_key_from_text(text)
        slot_label = (
            "A1" if slot_key == "0"
            else "A2" if slot_key == "1"
            else "A3" if slot_key == "2"
            else "A4" if slot_key == "3"
            else "Зовнішній (VT)"
        )

        spools = await app.storage.load_spools()
        mounted_spool, rem_stock = assign_spool_to_slot(spools, selected_spool, target_p, slot_key)
        await app.storage.save_spools(spools)
        await app.save_printers_config()

        is_from_warehouse = (mount_src == "warehouse" or not selected_pid)
        if is_from_warehouse:
            user["state"] = "idle"
            user.get("context_data", {}).pop("selected_printer_id", None)
            user.get("context_data", {}).pop("mount_source", None)
            user.get("context_data", {}).pop("mount_spool", None)
            user.get("context_data", {}).pop("mount_printer_id", None)
            await app.storage.save_user(user)
            menu_kb = get_filament_menu_keyboard(lang=u_lang)
        else:
            user["state"] = "printer_menu"
            user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
            user.get("context_data", {}).pop("mount_spool", None)
            user.get("context_data", {}).pop("mount_printer_id", None)
            await app.storage.save_user(user)
            menu_kb = get_single_printer_filament_keyboard(lang=u_lang)

        stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
        stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

        await message.answer(
            f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [{slot_label}]!</b>{stock_info}"
            if u_lang != "en" else
            f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [{slot_label}]!</b>{stock_info_en}",
            parse_mode=ParseMode.HTML,
            reply_markup=menu_kb,
        )
        hw_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Так, завантажити" if u_lang != "en" else "✅ Yes, Load", callback_data=f"hw_load:{target_p.id}:{slot_key}"),
                InlineKeyboardButton(text="❌ Ні, пропустити" if u_lang != "en" else "❌ No, Skip", callback_data="hw_skip"),
            ]
        ])
        await message.answer(
            "❓ <b>Чи запустити функцію Load Filament на принтері?</b>"
            if u_lang != "en" else
            "❓ <b>Execute physical Load Filament on printer?</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=hw_kb,
        )
        return True

    if state == "select_slot_for_weight":
        if not target_printer:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Помилка: принтер не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        clean = text.lower().strip()
        is_valid_slot = (
            clean in ["1", "2", "3", "4", "vt", "a1", "a2", "a3", "a4"]
            or any(k in clean for k in ["a1", "slot 1", "слот 1", "слот a1", "a2", "slot 2", "слот 2", "слот a2", "a3", "slot 3", "слот 3", "слот a3", "a4", "slot 4", "слот 4", "слот a4", "зовнішн", "vt", "external", "котушкотримач"])
        )
        if not is_valid_slot:
            await message.answer(
                "⚠️ Невідомий слот. Оберіть слот зі списку на клавіатурі (наприклад: 📍 Слот A1 або Зовнішній):"
                if u_lang != "en" else
                "⚠️ Unknown slot. Please select a slot from the keyboard (e.g. 📍 Slot A1 or External):"
            )
            return True

        slot_key = parse_slot_key_from_text(text)
        slot_labels = {
            "0": "A1" if u_lang == "en" else "Слот A1",
            "1": "A2" if u_lang == "en" else "Слот A2",
            "2": "A3" if u_lang == "en" else "Слот A3",
            "3": "A4" if u_lang == "en" else "Слот A4",
            "254": "VT (External)" if u_lang == "en" else "VT (Зовнішній)",
        }
        s_label = slot_labels.get(slot_key, f"Слот {slot_key}")

        tray_info = (getattr(target_printer, "ams_trays_info", {}) or {}).get(str(slot_key), {})
        mat_info = tray_info.get("name") or tray_info.get("type") or ""
        spools = await app.storage.load_spools()
        for s in spools.values():
            if s.get("assigned_printer_id") == target_printer.id and str(s.get("assigned_slot_key")) in [str(slot_key), "255" if slot_key == "254" else str(slot_key)]:
                sp_name = s.get("name") or s.get("type")
                if sp_name:
                    mat_info = sp_name
                break

        slot_display = f"{s_label} — {mat_info}" if mat_info else s_label
        curr_g = target_printer.get_slot_grams(slot_key)
        user.setdefault("context_data", {})["edit_weight_slot_key"] = slot_key
        user["context_data"]["edit_weight_slot_label"] = s_label
        user["state"] = "edit_filament_weight"
        await app.storage.save_user(user)

        await message.answer(
            f"Поточний залишок для <b>{html.escape(target_printer.name)} ({slot_display})</b>: <b>{curr_g}g</b>\n\n"
            f"Введіть нову залишкову вагу філаменту в грамах (наприклад <code>850</code>):"
            if u_lang != "en"
            else f"Current remaining for <b>{html.escape(target_printer.name)} ({slot_display})</b>: <b>{curr_g}g</b>\n\n"
            f"Enter new filament remaining weight in grams (e.g. <code>850</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
                resize_keyboard=True,
            ),
        )
        return True

    if state == "select_spool_to_unmount":
        spools = await app.storage.load_spools()
        mounted_list = get_mounted_spools_or_trays(app, spools)

        selected_item = next(
            (m for m in mounted_list if m["button_text"] == text or text in m["button_text"] or m["slot_label"] in text or m["name"] in text),
            mounted_list[0] if len(mounted_list) == 1 else None,
        )
        if selected_item:
            p_id = selected_item["printer_id"]
            slot_k = selected_item["slot_key"]
            target_p = app.printers.get(p_id)

            res_desc, returned_to_batch = unassign_spool_from_slot(spools, selected_item, target_p, slot_k)
            await app.storage.save_spools(spools)

            if target_p:
                target_p.set_slot_grams(0.0, slot_id=slot_k)
                await app.save_printers_config()

            user["state"] = "printer_menu" if target_printer else "idle"
            await app.storage.save_user(user)

            kb = get_single_printer_filament_keyboard(lang=u_lang) if target_printer else get_filament_menu_keyboard(lang=u_lang)
            await message.answer(
                f"✅ <b>Котушку успішно знято: {res_desc}!</b>"
                if u_lang != "en" else
                f"✅ <b>Spool successfully unmounted: {res_desc}!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            hw_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Так, вивантажити" if u_lang != "en" else "✅ Yes, Unload", callback_data=f"hw_unload:{p_id}:{slot_k}"),
                    InlineKeyboardButton(text="❌ Ні, пропустити" if u_lang != "en" else "❌ No, Skip", callback_data="hw_skip"),
                ]
            ])
            await message.answer(
                "❓ <b>Чи запустити функцію Unload Filament на принтері?</b>"
                if u_lang != "en" else
                "❓ <b>Execute physical Unload Filament on printer?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=hw_kb,
            )
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    return False

