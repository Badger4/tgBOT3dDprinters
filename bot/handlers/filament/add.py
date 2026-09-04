"""
Add spool wizard handlers.
"""

import html
import uuid
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import get_filament_menu_keyboard, get_spool_presets_inline_keyboard
from functions.math_eval import safe_eval_math
from functions.filament_utils import extract_filament_type_from_name

router = Router()


@router.message(F.text.lower().in_(["➕ додати котушку", "додати котушку", "➕ додати", "додати", "➕ add spool", "add spool", "➕ add", "add"]))
async def handle_add_spool_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")

    user["state"] = "add_spool_name"
    user["context_data"]["new_spool"] = {}
    await app.storage.save_user(user)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")]],
        resize_keyboard=True,
    )
    await message.answer(
        "➕ <b>Додавання нової котушки на Склад</b>\n\n"
        "Введіть назву котушки (наприклад: <i>Bambu PLA Basic Black</i>) або оберіть готовий пресет нижче:"
        if u_lang != "en"
        else "➕ <b>Add new spool to stock</b>\n\n"
        "Enter spool name (e.g. <i>Bambu PLA Basic Black</i>) or select a preset below:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    presets = await app.storage.load_presets()
    if presets:
        await message.answer(
            "📋 <b>Швидкі пресети пластику:</b>" if u_lang != "en" else "📋 <b>Quick presets:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_spool_presets_inline_keyboard(presets, lang=u_lang),
        )


@router.callback_query(F.data.startswith("spool_preset:"))
async def handle_preset_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    p_id = callback.data.split(":", 1)[1]

    presets = await app.storage.load_presets()
    preset = presets.get(p_id)
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
        "remaining_grams": p_grams,
        "price_per_kg": p_price,
        "assigned_printer_id": None,
        "assigned_slot_key": None,
        "quantity": 1,
    }
    await app.storage.save_spools(spools)

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
    "add_spool_grams",
    "add_spool_price",
    "select_spool_to_mount",
    "select_printer_for_mount",
    "select_slot_for_mount",
    "select_spool_to_unmount",
    "select_spool_to_edit",
    "select_spool_field",
    "edit_spool_name",
    "edit_spool_type",
    "edit_spool_grams",
    "edit_spool_price",
    "select_spool_to_delete",
    "confirm_delete_spool",
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

    cancel_keywords = {"відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад", "cancel", "/cancel"}
    if text.lower() in cancel_keywords:
        user["state"] = "printer_menu" if target_printer else "idle"
        for k in ["new_spool", "edit_spool", "pending_spool", "delete_spool", "mount_spool", "mount_printer_id"]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        from bot.keyboards import get_printer_menu_keyboard, get_main_keyboard
        kb = get_printer_menu_keyboard(target_printer) if target_printer else get_main_keyboard(await app.is_user_admin(chat_id))
        await message.answer("Дію скасовано.", reply_markup=kb)
        return True

    if state == "add_spool_name":
        user.setdefault("context_data", {}).setdefault("new_spool", {})["name"] = text
        user["state"] = "add_spool_type"
        await app.storage.save_user(user)
        auto_type = extract_filament_type_from_name(text)
        await message.answer(
            f"🎨 <b>Оберіть або введіть тип пластику (наприклад: {auto_type}):</b>",
            parse_mode=ParseMode.HTML,
        )
        return True

    if state == "add_spool_type":
        user.setdefault("context_data", {}).setdefault("new_spool", {})["type"] = text.upper()
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)
        await message.answer("⚖️ <b>Введіть початкову вагу котушки у грамах (наприклад: 1000):</b>", parse_mode=ParseMode.HTML)
        return True

    if state == "add_spool_grams":
        val = safe_eval_math(text)
        g_val = float(val) if val is not None else 1000.0
        user.setdefault("context_data", {}).setdefault("new_spool", {})["remaining_grams"] = g_val
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)
        await message.answer("💰 <b>Введіть ціну за 1 кг у грн (наприклад: 850):</b>", parse_mode=ParseMode.HTML)
        return True

    if state == "add_spool_price":
        val = safe_eval_math(text)
        pr_val = float(val) if val is not None else 850.0
        new_spool = user.get("context_data", {}).get("new_spool", {})
        new_spool["price_per_kg"] = pr_val
        sp_name = new_spool.get("name", "Bambu Spool")
        sp_type = new_spool.get("type", "PLA")
        sp_grams = new_spool.get("remaining_grams", 1000.0)

        spools = await app.storage.load_spools()
        new_id = str(uuid.uuid4())
        spools[new_id] = {
            "id": new_id,
            "name": sp_name,
            "type": sp_type,
            "color": "#000000",
            "remaining_grams": sp_grams,
            "price_per_kg": pr_val,
            "assigned_printer_id": None,
            "assigned_slot_key": None,
            "quantity": 1,
        }
        await app.storage.save_spools(spools)

        user["state"] = "idle"
        user.get("context_data", {}).pop("new_spool", None)
        await app.storage.save_user(user)
        await message.answer(f"✅ <b>Котушку {html.escape(sp_name)} успішно додано на Склад!</b>", parse_mode=ParseMode.HTML, reply_markup=get_filament_menu_keyboard(lang=u_lang))
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
                    from bot.keyboards import get_ams_slots_keyboard
                    await message.answer(
                        f"📍 <b>Оберіть слот AMS для {html.escape(target_p.name)}:</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_ams_slots_keyboard(target_p),
                    )
                else:
                    slot_key = "254"
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

                    from bot.keyboards import get_single_printer_filament_keyboard
                    await message.answer(
                        f"✅ <b>Котушку {html.escape(selected['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>",
                        parse_mode=ParseMode.HTML,
                        reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
                    )
            else:
                user["state"] = "select_printer_for_mount"
                await app.storage.save_user(user)
                from bot.keyboards import get_printers_keyboard
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
            from bot.keyboards import get_ams_slots_keyboard
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
            from bot.handlers.filament.mount import parse_slot_key_from_text
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

            spools = await app.storage.load_spools()
            for s_id, s in list(spools.items()):
                if s.get("assigned_printer_id") == target_p.id and str(s.get("assigned_slot_key")) == slot_key:
                    s["assigned_printer_id"] = None
                    s["assigned_slot_key"] = None
                    spools[s_id] = s

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

            user["state"] = "printer_menu"
            user["context_data"].pop("mount_spool", None)
            user["context_data"].pop("mount_printer_id", None)
            await app.storage.save_user(user)

            from bot.keyboards import get_single_printer_filament_keyboard
            await message.answer(
                f"✅ <b>Котушку {html.escape(selected_spool['name'])} встановлено на {html.escape(target_p.name)} [{slot_label}]!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
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

            if selected_item["type_source"] == "db_spool" and selected_item.get("spool_id"):
                target_spool = spools.get(selected_item["spool_id"])
                if target_spool:
                    target_spool["assigned_printer_id"] = None
                    target_spool["assigned_slot_key"] = None
                    target_spool["remaining_grams"] = selected_item["remaining_grams"]
                    spools[target_spool["id"]] = target_spool
            else:
                new_id = f"spool_{str(uuid.uuid4())[:8]}"
                p_price = float(getattr(target_p, "price_per_kg", 850.0) or 850.0)
                spools[new_id] = {
                    "id": new_id,
                    "name": selected_item["name"],
                    "type": selected_item["material"],
                    "remaining_grams": selected_item["remaining_grams"],
                    "price_per_kg": p_price,
                    "assigned_printer_id": None,
                    "assigned_slot_key": None,
                    "quantity": 1,
                }
            await app.storage.save_spools(spools)

            if target_p:
                target_p.set_slot_grams(0.0, slot_id=slot_k)
                await app.save_printers_config()

            user["state"] = "printer_menu"
            await app.storage.save_user(user)

            from bot.keyboards import get_single_printer_filament_keyboard
            await message.answer(
                f"✅ <b>Котушку успішно знято та повернуто на Склад!</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_single_printer_filament_keyboard(lang=u_lang),
            )
        return True

    return False

