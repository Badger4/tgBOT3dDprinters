"""
Add spool wizard handlers.
"""

import html
import uuid
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_filament_menu_keyboard,
    get_spool_presets_inline_keyboard,
    get_filament_types_keyboard,
    get_wizard_nav_keyboard,
    get_spool_edit_fields_keyboard,
    get_confirm_delete_spool_keyboard,
    get_printers_keyboard,
    get_ams_slots_keyboard,
    get_filament_colors_keyboard,
    get_spool_quantity_keyboard,
    get_single_printer_filament_keyboard,
    get_printer_menu_keyboard,
    get_spools_keyboard,
)
from utils.math_eval import safe_eval_math
from utils.filament_utils import (
    extract_filament_type_from_name,
    parse_filament_color,
    get_color_emoji,
    get_color_display_name,
)

DEFAULT_SPOOL_PRESETS = {
    "bambu_pla_black": {"name": "Bambu PLA Black", "type": "PLA", "color": "#000000", "price_per_kg": 850.0, "weight_g": 1000.0},
    "sunlu_pla_white": {"name": "Sunlu PLA White", "type": "PLA", "color": "#FFFFFF", "price_per_kg": 650.0, "weight_g": 1000.0},
    "esun_petg_grey": {"name": "eSUN PETG Grey", "type": "PETG", "color": "#808080", "price_per_kg": 700.0, "weight_g": 1000.0},
    "tpu_red": {"name": "TPU 95A Red", "type": "TPU", "color": "#EF4444", "price_per_kg": 950.0, "weight_g": 1000.0},
}

router = Router()



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


@router.message(F.text.lower().in_(["➕ додати котушку", "додати котушку", "➕ додати", "додати", "➕ add spool", "add spool", "➕ add", "add"]))
async def handle_add_spool_start(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "add_spool_name"
    user["context_data"]["new_spool"] = {}
    await app.storage.save_user(user)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати" if u_lang != "en" else "❌ Cancel")]],
        resize_keyboard=True,
    )
    await message.answer(
        "➕ <b>Додавання нової котушки на Склад</b>\n\n"
        "Введіть назву котушки (наприклад: <i>Bambu PLA Basic Black</i>):"
        if u_lang != "en"
        else "➕ <b>Add new spool to stock</b>\n\n"
        "Enter spool name (e.g. <i>Bambu PLA Basic Black</i>):",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("spool_preset:"))
async def handle_preset_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    p_id = callback.data.split(":", 1)[1]

    presets = await app.storage.load_presets()
    preset = presets.get(p_id) or DEFAULT_SPOOL_PRESETS.get(p_id)
    if not preset:
        await callback.answer("⚠️ Пресет не знайдено", show_alert=True)
        return

    spools = await app.storage.load_spools()
    new_id = str(uuid.uuid4())
    p_name = preset.get("name", "Bambu PLA")
    p_type = preset.get("type", extract_filament_type_from_name(p_name))
    p_grams = float(preset.get("weight_g") or preset.get("remaining_grams") or 1000.0)
    p_price = float(preset.get("price_per_kg") or preset.get("price_uah") or 850.0)
    p_color = preset.get("color", "#000000")

    spools[new_id] = {
        "id": new_id,
        "name": p_name,
        "type": p_type,
        "color": p_color,
        "initial_grams": p_grams,
        "remaining_grams": p_grams,
        "price_per_kg": p_price,
        "assigned_printer_id": None,
        "assigned_slot_key": None,
        "quantity": 1,
    }
    await app.storage.save_spools(spools)
    await app.storage.record_spool_movement(
        spool_id=new_id,
        spool_name=p_name,
        action="initial_stock",
        weight_change_g=p_grams,
        prev_weight_g=0.0,
        new_weight_g=p_grams,
        reason="Внесення на склад за пресетом (Telegram)",
        user=user.get("username") or user.get("first_name") or f"TG:{callback.from_user.id}",
    )

    user["state"] = "idle"
    user.get("context_data", {}).pop("new_spool", None)
    await app.storage.save_user(user)

    await callback.answer(f"✅ Додано: {p_name}")
    await callback.message.answer(
        f"✅ <b>Успішно додано котушку за пресетом!</b>\n\n"
        f"📦 Назва: <b>{html.escape(p_name)}</b>\n"
        f"🎨 Тип: <b>{html.escape(p_type)}</b>\n"
        f"⚖️ Вага: <b>{p_grams}g</b>\n"
        f"💰 Ціна: <b>{p_price} грн/кг</b>"
        if u_lang != "en"
        else f"✅ <b>Spool added from preset!</b>\n\n"
        f"📦 Name: <b>{html.escape(p_name)}</b>\n"
        f"🎨 Type: <b>{html.escape(p_type)}</b>\n"
        f"⚖️ Weight: <b>{p_grams}g</b>\n"
        f"💰 Price: <b>{p_price} UAH/kg</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_menu_keyboard(lang=u_lang),
    )


FILAMENT_STATES = {
    "add_spool_name",
    "add_spool_type",
    "add_spool_color",
    "add_spool_grams",
    "add_spool_price",
    "add_spool_quantity",
    "select_spool_to_mount",
    "select_printer_for_mount",
    "select_slot_for_mount",
    "select_slot_for_weight",
    "select_spool_to_unmount",
    "select_spool_to_edit",
    "select_spool_field",
    "edit_spool_name",
    "edit_spool_type",
    "edit_spool_color",
    "edit_spool_grams",
    "edit_spool_price",
    "edit_spool_quantity",
    "select_spool_to_delete",
    "confirm_delete_spool",
    "edit_filament_weight",
    "edit_filament_price",
}


async def filament_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") in FILAMENT_STATES


@router.message(filament_state_filter)
async def handle_filament_states(message: Message, app) -> bool:
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    state = user.get("state", "idle")
    text = message.text.strip() if message.text else ""
    ctx_data = user.get("context_data", {})
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    step_back_keywords = {"↩️ крок назад", "крок назад", "step back", "↩️ step back"}
    if text.strip().lower() in step_back_keywords:
        if state == "add_spool_type":
            cur_name = user.get("context_data", {}).get("new_spool", {}).get("name", "")
            user["state"] = "add_spool_name"
            await app.storage.save_user(user)
            kb = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="❌ Скасувати" if u_lang != "en" else "❌ Cancel")]],
                resize_keyboard=True,
            )
            prompt = (
                f"📝 <b>Введіть назву котушки</b> (попередня: <i>{html.escape(cur_name)}</i>):"
                if u_lang != "en"
                else f"📝 <b>Enter spool name</b> (previous: <i>{html.escape(cur_name)}</i>):"
            )
            await message.answer(prompt, parse_mode=ParseMode.HTML, reply_markup=kb)
            return True

        if state == "add_spool_color":
            cur_type = user.get("context_data", {}).get("new_spool", {}).get("type", "PLA")
            user["state"] = "add_spool_type"
            await app.storage.save_user(user)
            prompt = (
                f"🎨 <b>Оберіть або введіть тип пластику</b> (попередній: <b>{html.escape(cur_type)}</b>):"
                if u_lang != "en"
                else f"🎨 <b>Select or enter filament type</b> (previous: <b>{html.escape(cur_type)}</b>):"
            )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_types_keyboard(lang=u_lang, include_step_back=True),
            )
            return True

        if state == "add_spool_grams":
            cur_sp = user.get("context_data", {}).get("new_spool", {})
            cur_col = get_color_display_name(cur_sp, lang=u_lang)
            user["state"] = "add_spool_color"
            await app.storage.save_user(user)
            prompt = (
                f"🌈 <b>Оберіть або введіть колір пластику</b> (попередній: <b>{cur_col}</b>):"
                if u_lang != "en"
                else f"🌈 <b>Select or enter filament color</b> (previous: <b>{cur_col}</b>):"
            )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_colors_keyboard(lang=u_lang, include_step_back=True),
            )
            return True

        if state == "add_spool_price":
            cur_grams = user.get("context_data", {}).get("new_spool", {}).get("remaining_grams", 1000.0)
            user["state"] = "add_spool_grams"
            await app.storage.save_user(user)
            prompt = (
                f"⚖️ <b>Введіть початкову вагу котушки у грамах</b> (попередня: <code>{cur_grams}g</code>):"
                if u_lang != "en"
                else f"⚖️ <b>Enter spool weight in grams</b> (previous: <code>{cur_grams}g</code>):"
            )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_nav_keyboard(lang=u_lang),
            )
            return True

        if state == "add_spool_quantity":
            cur_pr = user.get("context_data", {}).get("new_spool", {}).get("price_per_kg", 850.0)
            user["state"] = "add_spool_price"
            await app.storage.save_user(user)
            prompt = (
                f"💰 <b>Введіть ціну за 1 кг у грн</b> (попередня: <code>{cur_pr} грн</code>):"
                if u_lang != "en"
                else f"💰 <b>Enter price per 1 kg in UAH</b> (previous: <code>{cur_pr} UAH</code>):"
            )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_nav_keyboard(lang=u_lang),
            )
            return True

    cancel_keywords = {
        "відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад",
        "cancel", "/cancel", "back", "⬅️ back", "❌ скасувати", "❌ cancel"
    }
    if text.lower() in cancel_keywords:
        user["state"] = "printer_menu" if target_printer else "idle"
        for k in ["new_spool", "edit_spool", "edit_spool_id", "pending_spool", "delete_spool", "delete_spool_id", "mount_spool", "mount_printer_id", "edit_weight_slot_key", "edit_weight_slot_label"]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        kb = get_single_printer_filament_keyboard(lang=u_lang) if (target_printer and (state.startswith("edit_filament") or state.startswith("select_slot_for_weight"))) else (get_printer_menu_keyboard(target_printer, lang=u_lang) if target_printer else get_filament_menu_keyboard(lang=u_lang))
        await message.answer("Дію скасовано." if u_lang != "en" else "Action cancelled.", reply_markup=kb)
        return True

    if state == "add_spool_name":
        if not text:
            await message.answer("⚠️ Введіть назву котушки:" if u_lang != "en" else "⚠️ Enter spool name:")
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["name"] = text
        user["state"] = "add_spool_type"
        await app.storage.save_user(user)
        await message.answer(
            "🎨 <b>Оберіть або введіть тип пластику (наприклад: PLA):</b>"
            if u_lang != "en" else
            "🎨 <b>Select or enter filament type (e.g. PLA):</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_types_keyboard(lang=u_lang, include_step_back=True),
        )
        return True

    if state == "add_spool_type":
        if not text:
            await message.answer("⚠️ Введіть тип пластику:" if u_lang != "en" else "⚠️ Enter filament type:")
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["type"] = text.upper()
        user["state"] = "add_spool_color"
        await app.storage.save_user(user)
        await message.answer(
            "🌈 <b>Оберіть або введіть колір пластику:</b>"
            if u_lang != "en" else
            "🌈 <b>Select or enter filament color:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_colors_keyboard(lang=u_lang, include_step_back=True),
        )
        return True

    if state == "add_spool_color":
        if not text:
            await message.answer("⚠️ Оберіть або введіть колір:" if u_lang != "en" else "⚠️ Select or enter color:")
            return True
        hex_code, color_label = parse_filament_color(text)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["color"] = hex_code
        user.setdefault("context_data", {}).setdefault("new_spool", {})["color_name"] = color_label
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)
        await message.answer(
            "⚖️ <b>Введіть початкову вагу котушки у грамах (наприклад: 1000):</b>"
            if u_lang != "en" else
            "⚖️ <b>Enter spool weight in grams (e.g. 1000):</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_nav_keyboard(lang=u_lang),
        )
        return True

    if state == "add_spool_grams":
        clean_text = text.replace("g", "").replace("г", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            await message.answer(
                "⚠️ Будь ласка, введіть коректну вагу у грамах (додатнє число, наприклад: <code>1000</code>):"
                if u_lang != "en" else
                "⚠️ Please enter a valid weight in grams (positive number, e.g. <code>1000</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_nav_keyboard(lang=u_lang),
            )
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["remaining_grams"] = float(val)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["initial_grams"] = float(val)
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)
        await message.answer(
            "💰 <b>Введіть ціну за 1 кг у грн (наприклад: 850):</b>"
            if u_lang != "en" else
            "💰 <b>Enter price per 1 кг in UAH (e.g. 850):</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_nav_keyboard(lang=u_lang),
        )
        return True

    if state == "add_spool_price":
        clean_text = text.replace("грн", "").replace("uah", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val < 0:
            await message.answer(
                "⚠️ Будь ласка, введіть коректну ціну у грн (додатнє число, наприклад: <code>850</code>):"
                if u_lang != "en" else
                "⚠️ Please enter a valid price in UAH (positive number, e.g. <code>850</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_wizard_nav_keyboard(lang=u_lang),
            )
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["price_per_kg"] = float(val)
        user["state"] = "add_spool_quantity"
        await app.storage.save_user(user)
        await message.answer(
            "📦 <b>Введіть кількість таких котушок на Складі (наприклад: 1 або 7):</b>"
            if u_lang != "en" else
            "📦 <b>Enter quantity of such spools in stock (e.g. 1 or 7):</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_spool_quantity_keyboard(lang=u_lang),
        )
        return True

    if state == "add_spool_quantity":
        clean_text = text.replace("шт", "").replace("pcs", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            await message.answer(
                "⚠️ Будь ласка, введіть коректну кількість (ціле додатнє число, наприклад: <code>1</code> або <code>7</code>):"
                if u_lang != "en" else
                "⚠️ Please enter a valid quantity (positive integer, e.g. <code>1</code> or <code>7</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_quantity_keyboard(lang=u_lang),
            )
            return True
        qty = int(val)
        new_spool = user.get("context_data", {}).get("new_spool", {})
        sp_name = new_spool.get("name", "Bambu Spool")
        sp_type = new_spool.get("type", "PLA")
        sp_color = new_spool.get("color", "#000000")
        sp_color_name = new_spool.get("color_name") or get_color_display_name(sp_color, lang=u_lang)
        sp_grams = new_spool.get("remaining_grams", 1000.0)
        init_grams = new_spool.get("initial_grams", sp_grams)
        pr_val = new_spool.get("price_per_kg", 850.0)

        spools = await app.storage.load_spools()
        new_id = str(uuid.uuid4())
        spools[new_id] = {
            "id": new_id,
            "name": sp_name,
            "type": sp_type,
            "color": sp_color,
            "color_name": sp_color_name,
            "initial_grams": init_grams,
            "remaining_grams": sp_grams,
            "price_per_kg": pr_val,
            "assigned_printer_id": None,
            "assigned_slot_key": None,
            "quantity": qty,
        }
        await app.storage.save_spools(spools)
        await app.storage.record_spool_movement(
            spool_id=new_id,
            spool_name=sp_name,
            action="initial_stock",
            weight_change_g=round(float(sp_grams) * qty, 2),
            prev_weight_g=0.0,
            new_weight_g=round(float(sp_grams), 2),
            reason=f"Внесення на склад через Telegram бот ({qty} шт)",
            user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
        )

        user["state"] = "idle"
        user.get("context_data", {}).pop("new_spool", None)
        await app.storage.save_user(user)

        color_disp = get_color_display_name({"color": sp_color, "color_name": sp_color_name}, lang=u_lang)
        await message.answer(
            f"✅ <b>Котушку {color_disp} {html.escape(sp_name)} успішно додано на Склад!</b>\n\n"
            f"🎨 Тип: <b>{html.escape(sp_type)}</b>\n"
            f"🌈 Колір: <b>{color_disp}</b>\n"
            f"⚖️ Вага: <b>{sp_grams}g</b>\n"
            f"💰 Ціна: <b>{pr_val} грн/кг</b>\n"
            f"📦 Кількість: <b>{qty} шт</b>"
            if u_lang != "en" else
            f"✅ <b>Spool {color_disp} {html.escape(sp_name)} added to stock!</b>\n\n"
            f"🎨 Type: <b>{html.escape(sp_type)}</b>\n"
            f"🌈 Color: <b>{color_disp}</b>\n"
            f"⚖️ Weight: <b>{sp_grams}g</b>\n"
            f"💰 Price: <b>{pr_val} UAH/kg</b>\n"
            f"📦 Quantity: <b>{qty} pcs</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

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
            qty_str = f" [📦 {qty} шт]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"

            if text in [exact_title, s_name, s_id] or text.strip() == s_name.strip():
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
            selected_pid = user.get("context_data", {}).get("selected_printer_id")
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

                    user["state"] = "printer_menu"
                    user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                    user["context_data"].pop("mount_spool", None)
                    user["context_data"].pop("mount_printer_id", None)
                    await app.storage.save_user(user)

                    stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
                    stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

                    await message.answer(
                        f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>{stock_info}"
                        if u_lang != "en" else
                        f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>{stock_info_en}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
                    )
            else:
                user["state"] = "select_printer_for_mount"
                await app.storage.save_user(user)
                await message.answer(
                    f"🖨️ <b>Оберіть принтер для установки котушки {html.escape(selected['name'])}:</b>"
                    if u_lang != "en" else
                    f"🖨️ <b>Select printer to mount spool {html.escape(selected['name'])}:</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_printers_keyboard(app.printers, lang=u_lang),
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

                user["state"] = "printer_menu"
                user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                user["context_data"].pop("mount_spool", None)
                user["context_data"].pop("mount_printer_id", None)
                await app.storage.save_user(user)

                stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
                stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

                await message.answer(
                    f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>{stock_info}"
                    if u_lang != "en" else
                    f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>{stock_info_en}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
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
        target_p = app.printers.get(p_id) if p_id else None

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

        from bot.handlers.filament.mount import parse_slot_key_from_text
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

        user["state"] = "printer_menu"
        user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
        user["context_data"].pop("mount_spool", None)
        user["context_data"].pop("mount_printer_id", None)
        await app.storage.save_user(user)

        stock_info = f"\n📦 Залишок на Складі: <b>{rem_stock} шт</b>" if rem_stock > 0 else ""
        stock_info_en = f"\n📦 Remaining in stock: <b>{rem_stock} pcs</b>" if rem_stock > 0 else ""

        await message.answer(
            f"✅ <b>Котушку {html.escape(mounted_spool['name'])} встановлено на {html.escape(target_p.name)} [{slot_label}]!</b>{stock_info}"
            if u_lang != "en" else
            f"✅ <b>Spool {html.escape(mounted_spool['name'])} mounted on {html.escape(target_p.name)} [{slot_label}]!</b>{stock_info_en}",
            parse_mode=ParseMode.HTML,
            reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
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

        from bot.handlers.filament.mount import parse_slot_key_from_text
        slot_key = parse_slot_key_from_text(text)
        slot_labels = {
            "0": "A1" if u_lang == "en" else "Слот A1",
            "1": "A2" if u_lang == "en" else "Слот A2",
            "2": "A3" if u_lang == "en" else "Слот A3",
            "3": "A4" if u_lang == "en" else "Слот A4",
            "254": "VT (External)" if u_lang == "en" else "VT (Зовнішній)",
        }
        s_label = slot_labels.get(slot_key, f"Слот {slot_key}")

        # Check tray material or mounted spool name
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
        from bot.handlers.filament.mount import get_mounted_spools_or_trays
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
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    if state == "select_spool_to_edit":
        spools = await app.storage.load_spools()
        candidate_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
        selected = None
        for s in candidate_spools:
            s_name = s.get("name", "Spool")
            s_grams = s.get("remaining_grams", 1000.0)
            s_type = s.get("type", "")
            qty = max(1, int(s.get("quantity", 1) or 1))
            color_emoji = get_color_emoji(s.get("color_name") or s.get("color", ""))
            c_prefix = f"{color_emoji} " if color_emoji else ""
            type_str = f"{s_type}, " if (s_type and s_type.lower() not in s_name.lower()) else ""
            qty_str = f" [📦 {qty} шт]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"

            if text in [exact_title, s_name, s.get("id")] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in candidate_spools:
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s.get("id") == text.strip()):
                    selected = s
                    break

        if selected:
            user["context_data"]["edit_spool_id"] = selected["id"]
            user["state"] = "select_spool_field"
            await app.storage.save_user(user)

            is_en = u_lang == "en"
            assigned_str = ""
            p_id = selected.get("assigned_printer_id")
            if p_id and p_id in app.printers:
                p = app.printers[p_id]
                assigned_str = (
                    f"\n🖨️ Встановлено на: <b>{html.escape(p.name)}</b> (Слот {selected.get('assigned_slot_key', 'VT')})"
                    if not is_en else
                    f"\n🖨️ Mounted on: <b>{html.escape(p.name)}</b> (Slot {selected.get('assigned_slot_key', 'VT')})"
                )

            color_val = selected.get("color_name") or selected.get("color", "")
            c_ico = get_color_emoji(color_val)
            c_disp = get_color_display_name(selected, lang=u_lang)
            qty_disp = f"{selected.get('quantity', 1)} шт" if not is_en else f"{selected.get('quantity', 1)} pcs"

            card = (
                f"✏️ <b>Редагування котушки: {c_ico} {html.escape(selected.get('name', 'Котушка'))}</b>\n\n"
                f"🏷️ <b>Назва:</b> {html.escape(selected.get('name', ''))}\n"
                f"🎨 <b>Тип:</b> {html.escape(selected.get('type', 'PLA'))}\n"
                f"🌈 <b>Колір:</b> {c_disp}\n"
                f"📦 <b>Кількість:</b> {qty_disp}\n"
                f"⚖️ <b>Залишок:</b> {selected.get('remaining_grams', 1000.0)}g\n"
                f"💰 <b>Ціна за 1 кг:</b> {selected.get('price_per_kg', 850.0)} грн"
                f"{assigned_str}\n\n"
                f"Оберіть параметр, який бажаєте змінити:"
                if not is_en else
                f"✏️ <b>Edit Spool: {c_ico} {html.escape(selected.get('name', 'Spool'))}</b>\n\n"
                f"🏷️ <b>Name:</b> {html.escape(selected.get('name', ''))}\n"
                f"🎨 <b>Type:</b> {html.escape(selected.get('type', 'PLA'))}\n"
                f"🌈 <b>Color:</b> {c_disp}\n"
                f"📦 <b>Quantity:</b> {qty_disp}\n"
                f"⚖️ <b>Remaining:</b> {selected.get('remaining_grams', 1000.0)}g\n"
                f"💰 <b>Price per 1 kg:</b> {selected.get('price_per_kg', 850.0)} UAH"
                f"{assigned_str}\n\n"
                f"Select parameter to modify:"
            )
            await message.answer(card, parse_mode=ParseMode.HTML, reply_markup=get_spool_edit_fields_keyboard(lang=u_lang))
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    if state == "select_spool_field":
        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        cur_spool = spools.get(spool_id)
        if not cur_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        kb_back = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]], resize_keyboard=True)
        low = text.lower()
        if any(k in low for k in ["назва", "name", "🏷️"]):
            user["state"] = "edit_spool_name"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть нову назву для <b>{html.escape(cur_spool.get('name', ''))}</b>:"
                if u_lang != "en" else
                f"Enter new name for <b>{html.escape(cur_spool.get('name', ''))}</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_back,
            )
        elif any(k in low for k in ["тип", "type", "🎨"]):
            user["state"] = "edit_spool_type"
            await app.storage.save_user(user)
            await message.answer(
                f"🎨 <b>Оберіть або введіть новий тип пластику</b>\n(поточний: <b>{html.escape(cur_spool.get('type', 'PLA'))}</b>):"
                if u_lang != "en" else
                f"🎨 <b>Select or enter new filament type</b>\n(current: <b>{html.escape(cur_spool.get('type', 'PLA'))}</b>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_types_keyboard(lang=u_lang, include_step_back=False),
            )
        elif any(k in low for k in ["колір", "color", "🌈"]):
            user["state"] = "edit_spool_color"
            await app.storage.save_user(user)
            cur_color_disp = get_color_display_name(cur_spool, lang=u_lang)
            await message.answer(
                f"🌈 <b>Оберіть або введіть новий колір пластику</b>\n(поточний: <b>{cur_color_disp}</b>):"
                if u_lang != "en" else
                f"🌈 <b>Select or enter new filament color</b>\n(current: <b>{cur_color_disp}</b>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_colors_keyboard(lang=u_lang, include_step_back=False),
            )
        elif any(k in low for k in ["кількість", "quantity", "📦"]):
            user["state"] = "edit_spool_quantity"
            await app.storage.save_user(user)
            await message.answer(
                f"📦 <b>Введіть кількість таких котушок на Складі</b>\n(поточна: <b>{cur_spool.get('quantity', 1)} шт</b>, наприклад: <code>1</code> або <code>7</code>):"
                if u_lang != "en" else
                f"📦 <b>Enter spool quantity in stock</b>\n(current: <b>{cur_spool.get('quantity', 1)} pcs</b>, e.g. <code>1</code> or <code>7</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_quantity_keyboard(lang=u_lang),
            )
        elif any(k in low for k in ["залишок", "вага", "remaining", "weight", "⚖️"]):
            user["state"] = "edit_spool_grams"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть новий залишок у грамах (поточний: <b>{cur_spool.get('remaining_grams', 1000.0)}g</b>, наприклад: <code>850</code>):"
                if u_lang != "en" else
                f"Enter new remaining weight in grams (current: <b>{cur_spool.get('remaining_grams', 1000.0)}g</b>, e.g. <code>850</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_back,
            )
        elif any(k in low for k in ["вартість", "ціна", "price", "💰"]):
            user["state"] = "edit_spool_price"
            await app.storage.save_user(user)
            await message.answer(
                f"Введіть нову ціну за 1 кг у грн (поточна: <b>{cur_spool.get('price_per_kg', 850.0)} грн</b>):"
                if u_lang != "en" else
                f"Enter new price per 1 kg in UAH (current: <b>{cur_spool.get('price_per_kg', 850.0)} UAH</b>):",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_back,
            )
        else:
            await message.answer(
                "⚠️ Будь ласка, оберіть параметр із клавіатури або натисніть «⬅️ Назад»."
                if u_lang != "en" else
                "⚠️ Please select a parameter from the keyboard or click «⬅️ Back»."
            )
        return True

    if state == "edit_spool_name":
        if not text:
            await message.answer("⚠️ Назва не може бути порожньою. Введіть назву котушки:")
            return True
        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        target_spool["name"] = text
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Назву котушки змінено на «{html.escape(text)}»!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool name updated to «{html.escape(text)}»!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "edit_spool_type":
        if not text:
            await message.answer("⚠️ Тип не може бути порожнім. Введіть тип пластику:")
            return True
        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        new_t = text.upper()
        target_spool["type"] = new_t
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        p_id = target_spool.get("assigned_printer_id")
        if p_id and p_id in app.printers:
            app.printers[p_id].filament_type = new_t
            await app.save_printers_config()

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Тип пластику змінено на «{html.escape(new_t)}»!</b>"
            if u_lang != "en" else
            f"✅ <b>Filament type updated to «{html.escape(new_t)}»!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "edit_spool_color":
        if not text:
            await message.answer("⚠️ Оберіть або введіть колір:")
            return True
        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        hex_code, color_label = parse_filament_color(text)
        target_spool["color"] = hex_code
        target_spool["color_name"] = color_label
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        disp_col = get_color_display_name(target_spool, lang=u_lang)
        await message.answer(
            f"✅ <b>Колір котушки змінено на {disp_col}!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool color updated to {disp_col}!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "edit_spool_quantity":
        clean_text = text.replace("шт", "").replace("pcs", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            await message.answer(
                "⚠️ Будь ласка, введіть коректну кількість (ціле додатнє число, наприклад: <code>1</code> або <code>7</code>):"
                if u_lang != "en" else
                "⚠️ Please enter a valid quantity (positive integer, e.g. <code>1</code> or <code>7</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_quantity_keyboard(lang=u_lang),
            )
            return True

        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        new_qty = int(val)
        target_spool["quantity"] = new_qty
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Кількість котушок на Складі змінено на {new_qty} шт!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool quantity updated to {new_qty} pcs!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "edit_spool_grams":
        clean_text = text.replace("g", "").replace("г", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val < 0:
            await message.answer(
                "⚠️ Некоректне значення ваги. Будь ласка, введіть числове значення у грамах (наприклад: <code>850</code> або <code>1000 - 150</code>):"
                if u_lang != "en" else
                "⚠️ Invalid weight value. Please enter a number in grams (e.g. <code>850</code>):",
                parse_mode=ParseMode.HTML,
            )
            return True

        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        prev_g = float(target_spool.get("remaining_grams", 0.0))
        new_g = float(val)
        target_spool["remaining_grams"] = new_g
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        if abs(new_g - prev_g) > 0.01:
            delta = new_g - prev_g
            action = "refill" if delta > 0 else "manual_edit"
            reason = "Поповнення котушки (Telegram)" if delta > 0 else "Ручне коригування ваги (Telegram)"
            await app.storage.record_spool_movement(
                spool_id=spool_id,
                spool_name=target_spool.get("name", "Котушка"),
                action=action,
                weight_change_g=round(delta, 2),
                prev_weight_g=round(prev_g, 2),
                new_weight_g=round(new_g, 2),
                reason=reason,
                user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
            )

        p_id = target_spool.get("assigned_printer_id")
        slot_k = target_spool.get("assigned_slot_key")
        if p_id and p_id in app.printers and slot_k:
            app.printers[p_id].set_slot_grams(new_g, slot_id=str(slot_k))
            await app.save_printers_config()

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Залишок котушки змінено на {new_g}g!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool remaining updated to {new_g}g!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "edit_spool_price":
        clean_text = text.replace("грн", "").replace("uah", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val < 0:
            await message.answer(
                "⚠️ Некоректна ціна. Будь ласка, введіть числове значення у грн (наприклад: <code>850</code>):"
                if u_lang != "en" else
                "⚠️ Invalid price. Please enter a number in UAH (e.g. <code>850</code>):",
                parse_mode=ParseMode.HTML,
            )
            return True

        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        target_spool = spools.get(spool_id)
        if not target_spool:
            user["state"] = "idle"
            await app.storage.save_user(user)
            await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
            return True

        new_pr = float(val)
        target_spool["price_per_kg"] = new_pr
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

        user["state"] = "idle"
        user.get("context_data", {}).pop("edit_spool_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Вартість 1 кг пластику встановлено на {new_pr} грн!</b>"
            if u_lang != "en" else
            f"✅ <b>Price per 1 kg updated to {new_pr} UAH!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    if state == "select_spool_to_delete":
        spools = await app.storage.load_spools()
        candidate_spools = [s for s in spools.values() if not s.get("assigned_printer_id")]
        selected = None
        for s in candidate_spools:
            s_name = s.get("name", "Spool")
            s_grams = s.get("remaining_grams", 1000.0)
            s_type = s.get("type", "")
            qty = max(1, int(s.get("quantity", 1) or 1))
            color_emoji = get_color_emoji(s.get("color_name") or s.get("color", ""))
            c_prefix = f"{color_emoji} " if color_emoji else ""
            type_str = f"{s_type}, " if (s_type and s_type.lower() not in s_name.lower()) else ""
            qty_str = f" [📦 {qty} шт]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"

            if text in [exact_title, s_name, s.get("id")] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in candidate_spools:
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s.get("id") == text.strip()):
                    selected = s
                    break

        if selected:
            user["context_data"]["delete_spool_id"] = selected["id"]
            user["state"] = "confirm_delete_spool"
            await app.storage.save_user(user)

            await message.answer(
                f"⚠️ <b>Ви впевнені, що хочете видалити котушку «{html.escape(selected.get('name', ''))}» ({selected.get('remaining_grams', 1000.0)}g)?</b>"
                if u_lang != "en" else
                f"⚠️ <b>Are you sure you want to delete spool «{html.escape(selected.get('name', ''))}» ({selected.get('remaining_grams', 1000.0)}g)?</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_confirm_delete_spool_keyboard(lang=u_lang),
            )
        else:
            await message.answer(
                "⚠️ Оберіть котушку зі списку на клавіатурі."
                if u_lang != "en" else
                "⚠️ Please select a spool from the keyboard list."
            )
        return True

    if state == "confirm_delete_spool":
        spool_id = ctx_data.get("delete_spool_id")
        spools = await app.storage.load_spools()
        low = text.lower()
        if any(k in low for k in ["так", "yes", "delete", "видалити"]):
            sp = spools.pop(spool_id, None) if spool_id else None
            if sp:
                p_id = sp.get("assigned_printer_id")
                slot_k = sp.get("assigned_slot_key")
                if p_id and p_id in app.printers and slot_k:
                    app.printers[p_id].set_slot_grams(0.0, slot_id=str(slot_k))
                    await app.save_printers_config()
                await app.storage.save_spools(spools)

                prev_w = float(sp.get("remaining_grams", 0.0))
                await app.storage.record_spool_movement(
                    spool_id=spool_id,
                    spool_name=sp.get("name", "Котушка"),
                    action="write_off",
                    weight_change_g=-prev_w,
                    prev_weight_g=prev_w,
                    new_weight_g=0.0,
                    reason="Списання / Видалення котушки зі складу (Telegram)",
                    user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
                )

                user["state"] = "idle"
                user.get("context_data", {}).pop("delete_spool_id", None)
                await app.storage.save_user(user)

                await message.answer(
                    f"✅ <b>Котушку «{html.escape(sp.get('name', ''))}» успішно видалено!</b>"
                    if u_lang != "en" else
                    f"✅ <b>Spool «{html.escape(sp.get('name', ''))}» successfully deleted!</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_filament_menu_keyboard(lang=u_lang),
                )
            else:
                user["state"] = "idle"
                user.get("context_data", {}).pop("delete_spool_id", None)
                await app.storage.save_user(user)
                await message.answer("⚠️ Котушку не знайдено.", reply_markup=get_filament_menu_keyboard(lang=u_lang))
        else:
            user["state"] = "idle"
            user.get("context_data", {}).pop("delete_spool_id", None)
            await app.storage.save_user(user)
            await message.answer(
                "❌ Видалення котушки скасовано."
                if u_lang != "en" else
                "❌ Spool deletion cancelled.",
                reply_markup=get_filament_menu_keyboard(lang=u_lang),
            )
        return True

    if state == "edit_filament_weight" and target_printer:
        clean_text = text.replace("g", "").replace("г", "").strip()
        val = safe_eval_math(clean_text)
        if val is not None and val >= 0:
            slot_key = ctx_data.get("edit_weight_slot_key") or target_printer.get_active_slot_key()
            slot_lbl = ctx_data.get("edit_weight_slot_label")
            if not slot_lbl:
                slot_lbl = "VT" if str(slot_key) in ["254", "255"] else f"Слот A{int(slot_key)+1}"

            target_printer.set_slot_grams(float(val), slot_id=slot_key)
            if str(slot_key) == str(target_printer.get_active_slot_key()):
                target_printer.filament_grams = float(val)

            # Sync any mounted warehouse spool
            spools = await app.storage.load_spools()
            spool_updated = False
            for s_id, s in list(spools.items()):
                if s.get("assigned_printer_id") == target_printer.id and str(s.get("assigned_slot_key")) in [str(slot_key), "255" if str(slot_key) == "254" else str(slot_key)]:
                    prev_w = float(s.get("remaining_grams", 0.0))
                    new_w = float(val)
                    s["remaining_grams"] = new_w
                    spools[s_id] = s
                    spool_updated = True
                    if abs(new_w - prev_w) > 0.01:
                        delta = new_w - prev_w
                        await app.storage.record_spool_movement(
                            spool_id=s_id,
                            spool_name=s.get("name", "Котушка"),
                            action="refill" if delta > 0 else "manual_edit",
                            weight_change_g=round(delta, 2),
                            prev_weight_g=round(prev_w, 2),
                            new_weight_g=round(new_w, 2),
                            reason=f"Ручне коригування ваги слоту {slot_lbl} (Telegram)",
                            user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
                        )
                    break
            if spool_updated:
                await app.storage.save_spools(spools)

            await app.save_printers_config()
            user["state"] = "printer_menu"
            user.get("context_data", {}).pop("edit_weight_slot_key", None)
            user.get("context_data", {}).pop("edit_weight_slot_label", None)
            await app.storage.save_user(user)

            slot_suffix = f" ({slot_lbl})" if getattr(target_printer, "has_ams", False) else ""
            await message.answer(
                f"✅ Залишок філаменту для <b>{html.escape(target_printer.name)}{slot_suffix}</b> змінено на <b>{val}g</b>!"
                if u_lang != "en"
                else f"✅ Filament remaining for <b>{html.escape(target_printer.name)}{slot_suffix}</b> updated to <b>{val}g</b>!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
        else:
            await message.answer("⚠️ Будь ласка, введіть числове значення у грамах (наприклад: <code>750</code>):", parse_mode=ParseMode.HTML)
        return True

    if state == "edit_filament_price" and target_printer:
        clean_text = text.replace("грн", "").replace("uah", "").strip()
        val = safe_eval_math(clean_text)
        if val is not None and val >= 0:
            target_printer.price_per_kg = float(val)
            await app.save_printers_config()
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"✅ Вартість 1 кг пластику для {html.escape(target_printer.name)} встановлено на <b>{val} грн</b>!"
                if u_lang != "en"
                else f"✅ Price per 1 kg for {html.escape(target_printer.name)} set to <b>{val} UAH</b>!",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
        else:
            await message.answer("⚠️ Будь ласка, введіть числове значення ціни у грн (наприклад: <code>850</code>):", parse_mode=ParseMode.HTML)
        return True

    return False

