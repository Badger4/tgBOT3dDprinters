"""
Add spool wizard handlers.
"""

from __future__ import annotations

import html
import re
import uuid
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.handlers.filament.delete import DELETE_STATES, handle_delete_states
from bot.handlers.filament.edit import EDIT_STATES, handle_edit_states
from bot.handlers.filament.mount import (
    MOUNT_STATES,
    assign_spool_to_slot,
    handle_mount_states,
    unassign_spool_from_slot,
)
from bot.keyboards import (
    get_filament_colors_keyboard,
    get_filament_menu_keyboard,
    get_filament_types_keyboard,
    get_printer_menu_keyboard,
    get_single_printer_filament_keyboard,
    get_spool_presets_inline_keyboard,
    get_spool_price_keyboard,
    get_spool_quantity_keyboard,
    get_wizard_nav_keyboard,
)
from utils.filament_utils import (
    extract_filament_type_from_name,
    get_color_display_name,
    get_color_emoji,
    parse_filament_color,
)
from utils.math_eval import safe_eval_math

DEFAULT_SPOOL_PRESETS = {
    "bambu_pla_black": {"name": "Bambu PLA Black", "type": "PLA", "color": "#000000", "price_per_kg": 850.0, "weight_g": 1000.0},
    "sunlu_pla_white": {"name": "Sunlu PLA White", "type": "PLA", "color": "#FFFFFF", "price_per_kg": 650.0, "weight_g": 1000.0},
    "esun_petg_grey": {"name": "eSUN PETG Grey", "type": "PETG", "color": "#808080", "price_per_kg": 700.0, "weight_g": 1000.0},
    "tpu_red": {"name": "TPU 95A Red", "type": "TPU", "color": "#EF4444", "price_per_kg": 950.0, "weight_g": 1000.0},
}

router = Router()

GLOBAL_MENU_KEYWORDS = {
    "📊 стан ферми", "📊 farm status", "стан ферми", "farm status",
    "🖨️ принтери", "🖨️ printers", "принтери", "printers",
    "🧵 філамент", "🧵 filament", "філамент", "filament", "📦 склад", "📦 warehouse",
    "🧩 деталі", "🧩 parts", "деталі", "parts", "🧩 склад деталей",
    "📜 історія друку", "📜 print history", "історія друку", "print history",
    "💰 комерція", "💰 commercial", "комерція", "commercial",
    "🔔 сповіщення", "🔔 notifications", "сповіщення", "notifications",
    "👑 адмінка", "👑 admin panel", "адмінка", "admin",
}

CANCEL_KEYWORDS = {
    "відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад",
    "cancel", "/cancel", "back", "⬅️ back", "❌ скасувати", "❌ cancel",
    "головне меню", "⬅️ головне меню", "main menu", "⬅️ main menu",
    "повернутись в меню", "назад в меню", "⬅️ назад в меню",
}
STEP_BACK_KEYWORDS = {"↩️ крок назад", "крок назад", "step back", "↩️ step back"}

ADD_SPOOL_STATES = {
    "add_spool_name",
    "add_spool_type",
    "add_spool_color",
    "add_spool_grams",
    "add_spool_price",
    "add_spool_total_price",
    "add_spool_quantity",
    "confirm_quick_spool",
}

FILAMENT_STATES = {
    *ADD_SPOOL_STATES,
    *MOUNT_STATES,
    *EDIT_STATES,
    *DELETE_STATES,
}


def parse_quick_spool_text(text: str) -> dict | None:
    """
    Attempts to parse full spool info from a single text line, e.g.:
    'Bambu PLA Basic Black 1000g 850грн'
    'Sunlu PETG White 1kg 700 uah 2pcs'
    'eSUN PLA+ Grey 1000g 650 грн'
    Returns parsed dict or None if text is just a name.
    """
    if not text:
        return None
    raw = text.strip()

    weight_m = re.search(r'(?:^|\s)(\d+(?:[.,]\d+)?)\s*(kg|кг|g|г|gram|grams|грамм|грам)(?:\s|$|[,\.;])', raw, re.IGNORECASE)
    price_m = re.search(r'(?:^|\s)(\d+(?:[.,]\d+)?)\s*(?:грн|uah|₴|usd|\$|€|eur)(?:\s|$|[,\.;])', raw, re.IGNORECASE)

    if not weight_m and not price_m:
        return None

    weight_g = 1000.0
    if weight_m:
        try:
            val = float(weight_m.group(1).replace(",", "."))
            unit = weight_m.group(2).lower()
            weight_g = val * 1000.0 if unit in ["kg", "кг"] else val
        except (ValueError, TypeError):
            weight_g = 1000.0

    price_uah = 850.0
    if price_m:
        try:
            price_uah = float(price_m.group(1).replace(",", "."))
        except (ValueError, TypeError):
            price_uah = 850.0

    qty_m = re.search(r'(?:^|\s)(\d+)\s*(?:шт|pcs|x|х)(?:\s|$|[,\.;])', raw, re.IGNORECASE)
    qty = 1
    if qty_m:
        try:
            qty = max(1, int(qty_m.group(1)))
        except (ValueError, TypeError):
            qty = 1

    clean_name = raw
    if weight_m:
        clean_name = re.sub(re.escape(weight_m.group(0).strip()), "", clean_name, flags=re.IGNORECASE)
    if price_m:
        clean_name = re.sub(re.escape(price_m.group(0).strip()), "", clean_name, flags=re.IGNORECASE)
    if qty_m:
        clean_name = re.sub(re.escape(qty_m.group(0).strip()), "", clean_name, flags=re.IGNORECASE)
    clean_name = " ".join(clean_name.split()).strip(" ,.;-")

    fil_type = extract_filament_type_from_name(clean_name or raw)
    hex_code, color_label = parse_filament_color(clean_name or raw)

    if not clean_name:
        clean_name = f"Spool {fil_type} {color_label or ''}".strip()

    return {
        "name": clean_name,
        "type": fil_type,
        "color": hex_code,
        "color_name": color_label,
        "remaining_grams": weight_g,
        "initial_grams": weight_g,
        "price_per_kg": price_uah,
        "quantity": qty,
    }


@router.message(F.text.lower().in_(["➕ додати котушку", "додати котушку", "➕ додати", "додати", "➕ add spool", "add spool", "➕ add", "add"]))
async def handle_add_spool_start(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "add_spool_name"
    user.setdefault("context_data", {})["new_spool"] = {}
    await app.storage.save_user(user)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Скасувати" if u_lang != "en" else "❌ Cancel")]],
        resize_keyboard=True,
    )

    presets = await app.storage.load_presets()
    presets_kb = get_spool_presets_inline_keyboard(presets, lang=u_lang)

    text_uk = (
        "➕ <b>Додавання нової котушки на Склад</b>\n\n"
        "Введіть назву котушки (наприклад: <code>Bambu PLA Basic Black</code>):\n\n"
        "💡 <b>Розумне введення в один рядок:</b>\n"
        "Введіть усе разом: <code>Bambu PLA Black 1000g 850грн</code>\n\n"
        "⚡ <b>Або оберіть швидкий пресет в 1 клік нижче:</b>"
    )
    text_en = (
        "➕ <b>Add new spool to stock</b>\n\n"
        "Enter spool name (e.g. <code>Bambu PLA Basic Black</code>):\n\n"
        "💡 <b>Smart one-line input:</b>\n"
        "Enter all together: <code>Bambu PLA Black 1000g 850uah</code>\n\n"
        "⚡ <b>Or choose a 1-click quick preset below:</b>"
    )

    await message.answer(
        text_uk if u_lang != "en" else text_en,
        parse_mode=ParseMode.HTML,
        reply_markup=presets_kb,
    )
    await message.answer(
        "Введіть назву або 1 рядок:" if u_lang != "en" else "Enter name or 1-line text:",
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

    await callback.message.answer(
        f"✅ <b>Котушку додано за пресетом!</b>\n\n"
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
    if hasattr(callback, "answer"):
        try:
            await callback.answer("✅ Додано за пресетом!")
        except Exception:
            pass


@router.callback_query(F.data == "spool_quick_confirm")
async def handle_quick_spool_confirm_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spool_data = user.get("context_data", {}).get("new_spool")
    if not spool_data:
        await callback.answer("⚠️ Дані котушки застаріли", show_alert=True)
        return

    spools = await app.storage.load_spools()
    new_id = f"spool_{str(uuid.uuid4())[:8]}"
    spool_data["id"] = new_id
    spool_data["assigned_printer_id"] = None
    spool_data["assigned_slot_key"] = None
    spools[new_id] = spool_data
    await app.storage.save_spools(spools)

    grams = float(spool_data.get("remaining_grams", 1000.0))
    await app.storage.record_spool_movement(
        spool_id=new_id,
        spool_name=spool_data["name"],
        action="initial_stock",
        weight_change_g=grams,
        prev_weight_g=0.0,
        new_weight_g=grams,
        reason="Швидке додавання в 1 рядок (Telegram)",
        user=user.get("username") or user.get("first_name") or f"TG:{callback.from_user.id}",
    )

    user["state"] = "idle"
    user.get("context_data", {}).pop("new_spool", None)
    await app.storage.save_user(user)

    c_ico = get_color_emoji(spool_data.get("color_name") or spool_data.get("color", ""))
    await callback.message.edit_text(
        f"✅ <b>Котушку додано на Склад!</b>\n\n"
        f"📦 {c_ico} <b>{html.escape(spool_data['name'])}</b> ({spool_data['type']}, {grams:g}g)\n"
        f"💰 {spool_data['price_per_kg']:g} грн/кг • <b>{spool_data['quantity']} шт</b>"
        if u_lang != "en" else
        f"✅ <b>Spool added to stock!</b>\n\n"
        f"📦 {c_ico} <b>{html.escape(spool_data['name'])}</b> ({spool_data['type']}, {grams:g}g)\n"
        f"💰 {spool_data['price_per_kg']:g} UAH/kg • <b>{spool_data['quantity']} pcs</b>",
        parse_mode=ParseMode.HTML,
    )
    await callback.message.answer(
        "🧵 <b>Склад філаменту:</b>" if u_lang != "en" else "🧵 <b>Filament stock:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_menu_keyboard(lang=u_lang),
    )
    await callback.answer("✅ Додано на склад!")


@router.callback_query(F.data == "spool_quick_wizard")
async def handle_quick_spool_wizard_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spool_data = user.get("context_data", {}).get("new_spool", {})

    user["state"] = "add_spool_type"
    await app.storage.save_user(user)

    await callback.message.edit_text(
        f"✏️ <b>Покрокове налаштування котушки {html.escape(spool_data.get('name', ''))}</b>",
        parse_mode=ParseMode.HTML,
    )
    await callback.message.answer(
        f"🎨 <b>Оберіть тип пластику для {html.escape(spool_data.get('name', ''))}:</b>"
        if u_lang != "en"
        else f"🎨 <b>Select filament type for {html.escape(spool_data.get('name', ''))}:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_types_keyboard(lang=u_lang),
    )
    await callback.answer()


@router.callback_query(F.data == "spool_quick_cancel")
async def handle_quick_spool_cancel_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "idle"
    user.get("context_data", {}).pop("new_spool", None)
    await app.storage.save_user(user)

    await callback.message.edit_text("❌ Додавання котушки скасовано.")
    await callback.message.answer(
        "🧵 <b>Склад філаменту:</b>" if u_lang != "en" else "🧵 <b>Filament stock:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_filament_menu_keyboard(lang=u_lang),
    )
    await callback.answer("Скасовано")


async def filament_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    state = user.get("state")
    if state not in FILAMENT_STATES:
        return False

    text = message.text.strip().lower()
    if text in GLOBAL_MENU_KEYWORDS or (text.startswith("/") and text not in ["/cancel", "/back"]):
        # Reset state immediately so user is freed from wizard deadlock!
        user["state"] = "idle"
        for k in [
            "new_spool", "edit_spool", "edit_spool_id", "delete_spool", "delete_spool_id",
            "mount_spool", "mount_printer_id", "mount_source", "edit_weight_slot_key",
            "edit_weight_slot_label", "pending_spool",
        ]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        return False

    return True


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

    # Global menu button escape check (direct handler calls/safety)
    if text.lower() in GLOBAL_MENU_KEYWORDS or (text.startswith("/") and text.lower() not in ["/cancel", "/back"]):
        user["state"] = "idle"
        for k in [
            "new_spool", "edit_spool", "edit_spool_id", "delete_spool", "delete_spool_id",
            "mount_spool", "mount_printer_id", "mount_source", "edit_weight_slot_key",
            "edit_weight_slot_label", "pending_spool",
        ]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        return False

    # Global Cancel handling
    if text.lower() in CANCEL_KEYWORDS:
        if state in ["select_printer_for_mount", "select_slot_for_mount"] and text.lower() in ["назад", "⬅️ назад", "back", "⬅️ back"]:
            pass  # Fall through to state-specific step back in mount
        elif state in ["edit_spool_name", "edit_spool_type", "edit_spool_color", "edit_spool_quantity", "edit_spool_grams", "edit_spool_price"] and text.lower() in ["назад", "⬅️ назад", "back", "⬅️ back"]:
            pass  # Fall through to state-specific step back in edit
        else:
            mount_src = user.get("context_data", {}).get("mount_source")
            is_wh_cancel = (mount_src == "warehouse") or (not target_printer)
            user["state"] = "printer_menu" if (target_printer and not is_wh_cancel) else "idle"
            for k in [
                "new_spool", "edit_spool", "edit_spool_id", "pending_spool", "delete_spool",
                "delete_spool_id", "mount_spool", "mount_printer_id", "mount_source",
                "edit_weight_slot_key", "edit_weight_slot_label",
            ]:
                user.get("context_data", {}).pop(k, None)
            if is_wh_cancel:
                user.get("context_data", {}).pop("selected_printer_id", None)
            await app.storage.save_user(user)

            if is_wh_cancel:
                kb = get_filament_menu_keyboard(lang=u_lang)
            elif target_printer and (state.startswith("edit_filament") or state.startswith("select_slot_for_weight")):
                kb = get_single_printer_filament_keyboard(lang=u_lang)
            elif target_printer:
                kb = get_printer_menu_keyboard(target_printer, lang=u_lang)
            else:
                kb = get_filament_menu_keyboard(lang=u_lang)

            await message.answer("Дію скасовано." if u_lang != "en" else "Action cancelled.", reply_markup=kb)
            return True

    # Delegate to domain modules
    if state in MOUNT_STATES:
        return await handle_mount_states(message, app, user, state, text)

    if state in EDIT_STATES:
        return await handle_edit_states(message, app, user, state, text)

    if state in DELETE_STATES:
        return await handle_delete_states(message, app, user, state, text)

    # Handle Add Spool Wizard states
    return await _handle_add_spool_state(message, app, user, state, text, u_lang, ctx_data, target_printer)


async def _handle_add_spool_state(message: Message, app, user: dict, state: str, text: str, u_lang: str, ctx_data: dict, target_printer) -> bool:
    chat_id = str(message.chat.id)

    # Step Back navigation
    if text.strip().lower() in STEP_BACK_KEYWORDS:
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
                f"🎨 <b>Оберіть базовий колір або напишіть будь-який відтінок текстом</b> (попередній: <b>{cur_col}</b>):\n\n"
                "💡 <i>Наприклад: <code>бірюзовий</code>, <code>графіт</code>, <code>хакі</code>, <code>бордовий</code>, <code>м'ятний</code>, <code>лаванда</code>, <code>бежевий</code>, <code>золотий</code> чи HEX (<code>#0D9488</code>)</i>"
                if u_lang != "en"
                else f"🎨 <b>Select a base color or type any custom shade</b> (previous: <b>{cur_col}</b>):\n\n"
                "💡 <i>E.g.: <code>turquoise</code>, <code>graphite</code>, <code>khaki</code>, <code>burgundy</code>, <code>mint</code>, <code>lavender</code>, <code>beige</code>, <code>gold</code> or HEX (<code>#0D9488</code>)</i>"
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

        if state == "add_spool_total_price":
            user["state"] = "add_spool_price"
            await app.storage.save_user(user)
            cur_grams = float(user.get("context_data", {}).get("new_spool", {}).get("remaining_grams", 1000.0))
            cur_pr = float(user.get("context_data", {}).get("new_spool", {}).get("price_per_kg", 850.0))
            kg = cur_grams / 1000.0
            kg_str = f"{kg:g}"
            prompt = (
                f"💰 <b>Введіть ціну за 1 кг у грн</b> (попередня: <code>{cur_pr:.1f} грн</code>):"
                if u_lang != "en"
                else f"💰 <b>Enter price per 1 kg in UAH</b> (previous: <code>{cur_pr:.1f} UAH</code>):"
            )
            if u_lang != "en" and kg != 1:
                prompt += (
                    f"\n\n💡 <i>Підказка: вага вашої котушки — {cur_grams:g}г ({kg_str} кг).\n"
                    f"Щоб вказати ціну за всю котушку, введіть суму та розділіть на {kg_str} (наприклад: <code>1500/{kg_str}</code>).\n"
                    f"Або натисніть кнопку <b>«🏷️ Ціна за всю котушку»</b> нижче.</i>"
                )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_price_keyboard(cur_grams, lang=u_lang),
            )
            return True

        if state == "add_spool_quantity":
            cur_grams = float(user.get("context_data", {}).get("new_spool", {}).get("remaining_grams", 1000.0))
            cur_pr = float(user.get("context_data", {}).get("new_spool", {}).get("price_per_kg", 850.0))
            user["state"] = "add_spool_price"
            await app.storage.save_user(user)
            kg = cur_grams / 1000.0
            kg_str = f"{kg:g}"
            prompt = (
                f"💰 <b>Введіть ціну за 1 кг у грн</b> (попередня: <code>{cur_pr:.1f} грн</code>):"
                if u_lang != "en"
                else f"💰 <b>Enter price per 1 kg in UAH</b> (previous: <code>{cur_pr:.1f} UAH</code>):"
            )
            if u_lang != "en" and kg != 1:
                prompt += (
                    f"\n\n💡 <i>Підказка: вага вашої котушки — {cur_grams:g}г ({kg_str} кг).\n"
                    f"Щоб вказати ціну за всю котушку, введіть суму та розділіть на {kg_str} (наприклад: <code>1500/{kg_str}</code>).\n"
                    f"Або натисніть кнопку <b>«🏷️ Ціна за всю котушку»</b> нижче.</i>"
                )
            await message.answer(
                prompt,
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_price_keyboard(cur_grams, lang=u_lang),
            )
            return True

    # 1. State: add_spool_name
    if state == "add_spool_name":
        if not text:
            await message.answer("⚠️ Назва не може бути порожньою. Введіть назву котушки:")
            return True

        quick = parse_quick_spool_text(text)
        if quick:
            user.setdefault("context_data", {})["new_spool"] = quick
            user["state"] = "confirm_quick_spool"
            await app.storage.save_user(user)

            c_ico = get_color_emoji(quick.get("color_name") or quick.get("color", ""))
            c_name = quick.get("color_name") or "Не вказано"
            qty_str = f"{quick['quantity']} шт" if u_lang != "en" else f"{quick['quantity']} pcs"

            kb_quick = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Підтвердити і додати" if u_lang != "en" else "✅ Confirm & Add",
                            callback_data="spool_quick_confirm",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text="✏️ Покроково" if u_lang != "en" else "✏️ Step-by-step",
                            callback_data="spool_quick_wizard",
                        ),
                        InlineKeyboardButton(
                            text="❌ Скасувати" if u_lang != "en" else "❌ Cancel",
                            callback_data="spool_quick_cancel",
                        ),
                    ],
                ]
            )
            card = (
                f"⚡ <b>Швидке розпізнавання котушки:</b>\n\n"
                f"🏷️ Назва: <b>{html.escape(quick['name'])}</b>\n"
                f"🎨 Тип: <b>{html.escape(quick['type'])}</b>\n"
                f"🌈 Колір: {c_ico} <b>{c_name}</b>\n"
                f"⚖️ Вага: <b>{quick['remaining_grams']:g}g</b>\n"
                f"💰 Ціна за 1 кг: <b>{quick['price_per_kg']:g} грн</b>\n"
                f"📦 Кількість: <b>{qty_str}</b>\n\n"
                f"Зберегти цю котушку на Склад?"
                if u_lang != "en" else
                f"⚡ <b>Quick spool recognition:</b>\n\n"
                f"🏷️ Name: <b>{html.escape(quick['name'])}</b>\n"
                f"🎨 Type: <b>{html.escape(quick['type'])}</b>\n"
                f"🌈 Color: {c_ico} <b>{c_name}</b>\n"
                f"⚖️ Weight: <b>{quick['remaining_grams']:g}g</b>\n"
                f"💰 Price per 1 kg: <b>{quick['price_per_kg']:g} UAH</b>\n"
                f"📦 Quantity: <b>{qty_str}</b>\n\n"
                f"Save this spool to stock?"
            )
            await message.answer(card, parse_mode=ParseMode.HTML, reply_markup=kb_quick)
            return True

        user.setdefault("context_data", {})["new_spool"] = {"name": text}
        detected_type = extract_filament_type_from_name(text)
        if detected_type and detected_type != "PLA":
            user["context_data"]["new_spool"]["type"] = detected_type
        user["state"] = "add_spool_type"
        await app.storage.save_user(user)

        await message.answer(
            f"🎨 <b>Оберіть або введіть тип пластику для котушки «{html.escape(text)}»:</b>"
            if u_lang != "en"
            else f"🎨 <b>Select or enter filament type for «{html.escape(text)}»:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_types_keyboard(lang=u_lang),
        )
        return True

    # 2. State: add_spool_type
    if state == "add_spool_type":
        if not text:
            await message.answer("⚠️ Оберіть або введіть тип пластику:")
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["type"] = text.upper()
        user["state"] = "add_spool_color"
        await app.storage.save_user(user)

        cur_type = user["context_data"]["new_spool"]["type"]
        prompt = (
            f"🎨 <b>Оберіть базовий колір пластику ({cur_type}) або напишіть будь-який відтінок текстом:</b>\n\n"
            f"💡 <i>Наприклад: <code>бірюзовий</code>, <code>графіт</code>, <code>хакі</code>, <code>бордовий</code>, <code>м'ятний</code> або HEX (<code>#0D9488</code>)</i>"
            if u_lang != "en"
            else f"🎨 <b>Select a base filament color ({cur_type}) or enter any shade as text:</b>\n\n"
            f"💡 <i>E.g.: <code>turquoise</code>, <code>graphite</code>, <code>khaki</code>, <code>burgundy</code>, <code>mint</code> or HEX (<code>#0D9488</code>)</i>"
        )
        await message.answer(
            prompt,
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_colors_keyboard(lang=u_lang),
        )
        return True

    # 3. State: add_spool_color
    if state == "add_spool_color":
        if not text:
            await message.answer("⚠️ Оберіть або введіть колір:")
            return True
        hex_code, color_label = parse_filament_color(text)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["color"] = hex_code
        user["context_data"]["new_spool"]["color_name"] = color_label
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)

        disp_col = get_color_display_name(user["context_data"]["new_spool"], lang=u_lang)
        await message.answer(
            f"Колір розпізнано як: <b>{disp_col}</b>\n\n"
            f"Введіть початкову або залишкову вагу філаменту в грамах (наприклад <code>1000</code> або <code>850</code>):"
            if u_lang != "en"
            else f"Color recognized as: <b>{disp_col}</b>\n\n"
            f"Enter initial or remaining filament weight in grams (e.g. <code>1000</code> or <code>850</code>):",
            parse_mode=ParseMode.HTML,
            reply_markup=get_wizard_nav_keyboard(lang=u_lang),
        )
        return True

    # 4. State: add_spool_grams
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

        val = float(val)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["remaining_grams"] = val
        user["context_data"]["new_spool"]["initial_grams"] = val
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)

        kg = val / 1000.0
        kg_str = f"{kg:g}"
        prompt = (
            f"💰 <b>Введіть вартість 1 кг пластику у грн</b> (наприклад: <code>850</code>):"
            if u_lang != "en"
            else f"💰 <b>Enter cost of 1 kg filament in UAH</b> (e.g. <code>850</code>):"
        )
        if u_lang != "en" and kg != 1:
            prompt += (
                f"\n\n💡 <i>Підказка: вага вашої котушки — {val:g}г ({kg_str} кг).\n"
                f"Щоб вказати ціну за всю котушку, введіть суму та розділіть на {kg_str} (наприклад: <code>1500/{kg_str}</code>).\n"
                f"Або натисніть кнопку <b>«🏷️ Ціна за всю котушку»</b> нижче.</i>"
            )
        await message.answer(
            prompt,
            parse_mode=ParseMode.HTML,
            reply_markup=get_spool_price_keyboard(val, lang=u_lang),
        )
        return True

    # 5. State: add_spool_price
    if state == "add_spool_price":
        low = text.lower()
        if "ціна за всю котушку" in low or "price for entire spool" in low or "ціна за всю" in low:
            user["state"] = "add_spool_total_price"
            await app.storage.save_user(user)
            cur_g = float(user.get("context_data", {}).get("new_spool", {}).get("remaining_grams", 1000.0))
            await message.answer(
                f"🏷️ <b>Введіть вартість усієї котушки ({cur_g:g}г) у грн:</b>\n"
                f"(наприклад: <code>1500</code> або <code>450</code>):"
                if u_lang != "en"
                else f"🏷️ <b>Enter price for the entire spool ({cur_g:g}g) in UAH:</b>\n"
                f"(e.g. <code>1500</code> or <code>450</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="↩️ Крок назад" if u_lang != "en" else "↩️ Step back"), KeyboardButton(text="❌ Скасувати" if u_lang != "en" else "❌ Cancel")]],
                    resize_keyboard=True,
                ),
            )
            return True

        clean_text = text.replace("грн", "").replace("uah", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            cur_sp = user.get("context_data", {}).get("new_spool", {})
            cur_grams = float(cur_sp.get("remaining_grams", 1000.0))
            await message.answer(
                "⚠️ Будь ласка, введіть коректну ціну у грн (додатнє число або формула, наприклад: <code>850</code> чи <code>1500/3</code>):"
                if u_lang != "en" else
                "⚠️ Please enter a valid price in UAH (positive number or formula, e.g. <code>850</code> or <code>1500/3</code>):",
                parse_mode=ParseMode.HTML,
                reply_markup=get_spool_price_keyboard(cur_grams, lang=u_lang),
            )
            return True

        val = float(val)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["price_per_kg"] = val
        user["state"] = "add_spool_quantity"
        await app.storage.save_user(user)

        await message.answer(
            f"📦 <b>Введіть кількість таких котушок</b> (за замовчуванням <code>1</code> або оберіть кнопку нижче):"
            if u_lang != "en"
            else f"📦 <b>Enter spool quantity</b> (default <code>1</code> or select button below):",
            parse_mode=ParseMode.HTML,
            reply_markup=get_spool_quantity_keyboard(lang=u_lang),
        )
        return True

    # 6. State: add_spool_total_price
    if state == "add_spool_total_price":
        clean_text = text.replace("грн", "").replace("uah", "").strip()
        val = safe_eval_math(clean_text)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            await message.answer(
                "⚠️ Некоректна ціна. Будь ласка, введіть суму у грн (наприклад: <code>1500</code>):"
                if u_lang != "en"
                else "⚠️ Invalid price. Please enter amount in UAH (e.g. <code>1500</code>):",
                parse_mode=ParseMode.HTML,
            )
            return True

        total_price = float(val)
        cur_grams = float(user.get("context_data", {}).get("new_spool", {}).get("remaining_grams", 1000.0))
        price_per_kg = (total_price / (cur_grams / 1000.0)) if cur_grams > 0 else total_price

        user.setdefault("context_data", {}).setdefault("new_spool", {})["price_per_kg"] = round(price_per_kg, 1)
        user["state"] = "add_spool_quantity"
        await app.storage.save_user(user)

        await message.answer(
            f"✅ Вартість за всю котушку: <b>{total_price:g} грн</b>\n"
            f"Розраховано за 1 кг: <b>{round(price_per_kg, 1):g} грн/кг</b>\n\n"
            f"📦 <b>Введіть кількість таких котушок</b> (за замовчуванням <code>1</code> або оберіть кнопку нижче):"
            if u_lang != "en"
            else f"✅ Entire spool cost: <b>{total_price:g} UAH</b>\n"
            f"Calculated per 1 kg: <b>{round(price_per_kg, 1):g} UAH/kg</b>\n\n"
            f"📦 <b>Enter spool quantity</b> (default <code>1</code> or select button below):",
            parse_mode=ParseMode.HTML,
            reply_markup=get_spool_quantity_keyboard(lang=u_lang),
        )
        return True

    # 7. State: add_spool_quantity
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
        new_spool["quantity"] = qty

        spools = await app.storage.load_spools()
        new_id = f"spool_{str(uuid.uuid4())[:8]}"
        new_spool["id"] = new_id
        new_spool["assigned_printer_id"] = None
        new_spool["assigned_slot_key"] = None

        if "remaining_grams" not in new_spool:
            new_spool["remaining_grams"] = 1000.0
        if "initial_grams" not in new_spool:
            new_spool["initial_grams"] = new_spool["remaining_grams"]
        if "price_per_kg" not in new_spool:
            new_spool["price_per_kg"] = 850.0

        grams = float(new_spool["remaining_grams"])

        auto_mount = user.get("context_data", {}).get("auto_mount_on_create", False)
        target_pid = user.get("context_data", {}).get("target_printer_id")
        target_slot = user.get("context_data", {}).get("target_slot_key", "254")

        if auto_mount and target_pid and target_pid in app.printers:
            target_p = app.printers[target_pid]
            mounted_spool, rem_stock = assign_spool_to_slot(spools, new_spool, target_p, target_slot)
            await app.storage.save_spools(spools)
            await app.save_printers_config()

            await app.storage.record_spool_movement(
                spool_id=mounted_spool["id"],
                spool_name=mounted_spool["name"],
                action="initial_stock",
                weight_change_g=grams,
                prev_weight_g=0.0,
                new_weight_g=grams,
                reason="Внесення на склад (Telegram)",
                user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
            )

            user["state"] = "idle"
            for k in ["new_spool", "target_printer_id", "target_slot_key", "auto_mount_on_create", "prefill_type"]:
                user.get("context_data", {}).pop(k, None)
            await app.storage.save_user(user)

            slot_names = {"0": "A1", "1": "A2", "2": "A3", "3": "A4", "254": "VT"}
            s_label = slot_names.get(str(target_slot), f"Слот {target_slot}")
            stock_info = f"\n📦 Залишок на складі: {rem_stock} шт." if rem_stock > 0 else ""

            await message.answer(
                f"✅ <b>Котушку {html.escape(mounted_spool['name'])} створено та встановлено на {html.escape(target_p.name)} [{s_label}]!</b>{stock_info}"
                if u_lang != "en"
                else f"✅ <b>Spool {html.escape(mounted_spool['name'])} created and mounted on {html.escape(target_p.name)} [{s_label}]!</b>{stock_info}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_filament_menu_keyboard(lang=u_lang),
            )
            return True

        # Regular warehouse save
        spools[new_id] = new_spool
        await app.storage.save_spools(spools)

        await app.storage.record_spool_movement(
            spool_id=new_id,
            spool_name=new_spool["name"],
            action="initial_stock",
            weight_change_g=grams,
            prev_weight_g=0.0,
            new_weight_g=grams,
            reason="Внесення на склад (Telegram)",
            user=user.get("username") or user.get("first_name") or f"TG:{chat_id}",
        )

        user["state"] = "idle"
        user.get("context_data", {}).pop("new_spool", None)
        await app.storage.save_user(user)

        color_disp = get_color_display_name(new_spool, lang=u_lang)
        await message.answer(
            f"✅ <b>Котушку {color_disp} {html.escape(new_spool['name'])} успішно додано на Склад!</b>\n\n"
            f"🎨 Тип: <b>{html.escape(new_spool['type'])}</b>\n"
            f"🌈 Колір: <b>{color_disp}</b>\n"
            f"⚖️ Вага: <b>{new_spool['remaining_grams']}g</b>\n"
            f"💰 Ціна: <b>{new_spool['price_per_kg']} грн/кг</b>\n"
            f"📦 Кількість: <b>{qty} шт</b>"
            if u_lang != "en"
            else f"✅ <b>Spool {color_disp} {html.escape(new_spool['name'])} successfully added to stock!</b>\n\n"
            f"🎨 Type: <b>{html.escape(new_spool['type'])}</b>\n"
            f"🌈 Color: <b>{color_disp}</b>\n"
            f"⚖️ Weight: <b>{new_spool['remaining_grams']}g</b>\n"
            f"💰 Price: <b>{new_spool['price_per_kg']} UAH/kg</b>\n"
            f"📦 Quantity: <b>{qty} pcs</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
        return True

    return False


__all__ = [
    "router",
    "handle_add_spool_start",
    "handle_preset_callback",
    "handle_filament_states",
    "assign_spool_to_slot",
    "unassign_spool_from_slot",
    "DEFAULT_SPOOL_PRESETS",
]
