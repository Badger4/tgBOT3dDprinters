"""
Edit spool handlers.
"""

import html
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_ams_slots_keyboard,
    get_filament_colors_keyboard,
    get_filament_menu_keyboard,
    get_filament_types_keyboard,
    get_single_printer_filament_keyboard,
    get_spool_edit_fields_keyboard,
    get_spool_quantity_keyboard,
    get_spools_keyboard,
)
from utils.filament_utils import (
    get_color_display_name,
    get_color_emoji,
    parse_filament_color,
)
from utils.math_eval import safe_eval_math

router = Router()

CANCEL_KEYWORDS = {
    "відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад",
    "cancel", "/cancel", "back", "⬅️ back", "❌ скасувати", "❌ cancel",
    "головне меню", "⬅️ головне меню", "main menu", "⬅️ main menu",
    "повернутись в меню", "назад в меню", "⬅️ назад в меню",
}
STEP_BACK_KEYWORDS = {"↩️ крок назад", "крок назад", "step back", "↩️ step back", "⬅️ назад", "назад", "back", "⬅️ back"}

EDIT_STATES = {
    "select_spool_to_edit",
    "select_spool_field",
    "edit_spool_name",
    "edit_spool_type",
    "edit_spool_color",
    "edit_spool_quantity",
    "edit_spool_grams",
    "edit_spool_price",
    "edit_filament_weight",
    "edit_filament_price",
}


@router.message(F.text.lower().in_(["✏️ редагувати котушку", "редагувати котушку", "✏️ редагувати", "редагувати", "✏️ edit spool", "edit spool", "✏️ edit", "edit"]))
async def handle_edit_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    spools = await app.storage.load_spools()
    warehouse_spools = {s_id: s for s_id, s in spools.items() if not s.get("assigned_printer_id")}
    if not warehouse_spools:
        await message.answer(
            "⚠️ На Складі немає вільних котушок для редагування (усі встановлені на принтери або склад порожній)."
            if u_lang != "en"
            else "⚠️ No free spools available to edit in warehouse (all mounted or stock is empty)."
        )
        return

    user["state"] = "select_spool_to_edit"
    await app.storage.save_user(user)
    await message.answer(
        "✏️ <b>Оберіть котушку для редагування:</b>" if u_lang != "en" else "✏️ <b>Select spool to edit:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_spools_keyboard(warehouse_spools, lang=u_lang),
    )


@router.message(
    F.text.lower().in_(
        [
            "⚖️ змінити залишок ваги",
            "змінити залишок ваги",
            "✏️ ручне введення ваги",
            "ручне введення ваги",
            "✏️ manual weight input",
            "manual weight input",
            "✏️ змінити вагу",
            "змінити вагу",
            "✏️ edit weight",
            "edit weight",
        ]
    )
)
async def handle_manual_weight_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        await message.answer(
            "⚠️ Спочатку оберіть принтер у меню «🖨️ Принтери»."
            if u_lang != "en"
            else "⚠️ Please select a printer first in «🖨️ Printers»."
        )
        return

    if getattr(target_printer, "has_ams", False):
        user["state"] = "select_slot_for_weight"
        await app.storage.save_user(user)
        await message.answer(
            f"📍 <b>Оберіть слот AMS або зовнішній слот (VT) для зміни залишку ваги принтера {html.escape(target_printer.name)}:</b>"
            if u_lang != "en"
            else f"📍 <b>Select AMS slot or external slot (VT) to edit remaining weight for {html.escape(target_printer.name)}:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_ams_slots_keyboard(target_printer, lang=u_lang),
        )
        return

    user.setdefault("context_data", {})["edit_weight_slot_key"] = "254"
    user.setdefault("context_data", {})["edit_weight_slot_label"] = "VT"
    user["state"] = "edit_filament_weight"
    await app.storage.save_user(user)
    await message.answer(
        f"Поточний залишок для <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.filament_grams}g</b>\n\n"
        f"Введіть нову залишкову вагу філаменту в грамах (наприклад <code>850</code>):"
        if u_lang != "en"
        else f"Current remaining for <b>{html.escape(target_printer.name)}</b>: <b>{target_printer.filament_grams}g</b>\n\n"
        f"Enter new filament remaining weight in grams (e.g. <code>850</code>):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
            resize_keyboard=True,
        ),
    )

@router.message(F.text.lower().in_(["💰 ціна 1 кг (грн)", "ціна 1 кг (грн)", "💰 price 1 kg", "price 1 kg"]))
async def handle_manual_price_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    selected_pid = user.get("context_data", {}).get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    if not target_printer:
        return

    user["state"] = "edit_filament_price"
    await app.storage.save_user(user)
    await message.answer(
        f"Введіть вартість 1 кг пластику у грн для <b>{html.escape(target_printer.name)}</b> (поточна: {getattr(target_printer, 'price_per_kg', 850.0)} грн):"
        if u_lang != "en"
        else f"Enter cost of 1 kg filament in UAH for <b>{html.escape(target_printer.name)}</b> (current: {getattr(target_printer, 'price_per_kg', 850.0)} UAH):",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
            resize_keyboard=True,
        ),
    )


async def handle_edit_states(message: Message, app, user: dict, state: str, text: str) -> bool:
    chat_id = str(message.chat.id)
    u_lang = user.get("language", "uk")
    ctx_data = user.get("context_data", {})
    selected_pid = ctx_data.get("selected_printer_id")
    target_printer = app.printers.get(selected_pid) if selected_pid else None

    # Step back from an edit field to select_spool_field
    if state in ["edit_spool_name", "edit_spool_type", "edit_spool_color", "edit_spool_quantity", "edit_spool_grams", "edit_spool_price"] and text.strip().lower() in STEP_BACK_KEYWORDS:
        spool_id = ctx_data.get("edit_spool_id")
        spools = await app.storage.load_spools()
        cur_spool = spools.get(spool_id)
        if cur_spool:
            user["state"] = "select_spool_field"
            await app.storage.save_user(user)
            c_ico = get_color_emoji(cur_spool.get("color_name") or cur_spool.get("color", ""))
            c_disp = get_color_display_name(cur_spool, lang=u_lang)
            qty_disp = f"{cur_spool.get('quantity', 1)} шт" if u_lang != "en" else f"{cur_spool.get('quantity', 1)} pcs"
            card = (
                f"✏️ <b>Редагування котушки: {c_ico} {html.escape(cur_spool.get('name', 'Котушка'))}</b>\n\n"
                f"🏷️ <b>Назва:</b> {html.escape(cur_spool.get('name', ''))}\n"
                f"🎨 <b>Тип:</b> {html.escape(cur_spool.get('type', 'PLA'))}\n"
                f"🌈 <b>Колір:</b> {c_disp}\n"
                f"📦 <b>Кількість:</b> {qty_disp}\n"
                f"⚖️ <b>Залишок:</b> {cur_spool.get('remaining_grams', 1000.0)}g\n"
                f"💰 <b>Ціна за 1 кг:</b> {cur_spool.get('price_per_kg', 850.0)} грн\n\n"
                f"Оберіть параметр, який бажаєте змінити:"
                if u_lang != "en" else
                f"✏️ <b>Edit Spool: {c_ico} {html.escape(cur_spool.get('name', 'Spool'))}</b>\n\n"
                f"🏷️ <b>Name:</b> {html.escape(cur_spool.get('name', ''))}\n"
                f"🎨 <b>Type:</b> {html.escape(cur_spool.get('type', 'PLA'))}\n"
                f"🌈 <b>Color:</b> {c_disp}\n"
                f"📦 <b>Quantity:</b> {qty_disp}\n"
                f"⚖️ <b>Remaining:</b> {cur_spool.get('remaining_grams', 1000.0)}g\n"
                f"💰 <b>Price per 1 kg:</b> {cur_spool.get('price_per_kg', 850.0)} UAH\n\n"
                f"Select parameter to modify:"
            )
            await message.answer(card, parse_mode=ParseMode.HTML, reply_markup=get_spool_edit_fields_keyboard(lang=u_lang))
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
            qty_unit = "pcs" if u_lang == "en" else "шт"
            qty_str = f" [📦 {qty} {qty_unit}]" if qty > 1 else ""
            qty_str_alt = f" [📦 {qty} {'шт' if qty_unit == 'pcs' else 'pcs'}]" if qty > 1 else ""
            exact_title = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str}"
            exact_title_alt = f"🧵 {c_prefix}{s_name} ({type_str}{s_grams}g){qty_str_alt}"

            if text in [exact_title, exact_title_alt, s_name, s.get("id")] or text.strip() == s_name.strip():
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
            prompt = (
                f"🎨 <b>Оберіть базовий колір або напишіть будь-який відтінок текстом:</b>\n"
                f"(поточний: <b>{cur_color_disp}</b>)\n\n"
                f"💡 <i>Наприклад: <code>бірюзовий</code>, <code>графіт</code>, <code>хакі</code>, <code>бордовий</code>, <code>м'ятний</code> або HEX (<code>#0D9488</code>)</i>"
                if u_lang != "en" else
                f"🎨 <b>Select a base color or enter shade as text:</b>\n"
                f"(current: <b>{cur_color_disp}</b>)\n\n"
                f"💡 <i>E.g.: <code>turquoise</code>, <code>graphite</code>, <code>khaki</code>, <code>burgundy</code>, <code>mint</code> or HEX (<code>#0D9488</code>)</i>"
            )
            await message.answer(
                prompt,
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


