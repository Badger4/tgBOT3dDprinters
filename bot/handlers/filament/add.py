"""
Add spool wizard handlers.
"""

import html
import uuid
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery, KeyboardButton, Message, ReplyKeyboardMarkup
from bot.keyboards import (
    get_filament_menu_keyboard,
    get_spool_presets_inline_keyboard,
    get_spool_edit_fields_keyboard,
    get_confirm_delete_spool_keyboard,
    get_printers_keyboard,
    get_ams_slots_keyboard,
    get_single_printer_filament_keyboard,
    get_printer_menu_keyboard,
    get_spools_keyboard,
)
from utils.math_eval import safe_eval_math
from utils.filament_utils import extract_filament_type_from_name

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

    cancel_keywords = {
        "відміна", "відмінити", "скасувати", "стоп", "назад", "⬅️ назад",
        "cancel", "/cancel", "back", "⬅️ back", "❌ скасувати", "❌ cancel"
    }
    if text.lower() in cancel_keywords:
        user["state"] = "printer_menu" if target_printer else "idle"
        for k in ["new_spool", "edit_spool", "edit_spool_id", "pending_spool", "delete_spool", "delete_spool_id", "mount_spool", "mount_printer_id"]:
            user.get("context_data", {}).pop(k, None)
        await app.storage.save_user(user)
        kb = get_printer_menu_keyboard(target_printer, lang=u_lang) if target_printer else get_filament_menu_keyboard(lang=u_lang)
        await message.answer("Дію скасовано." if u_lang != "en" else "Action cancelled.", reply_markup=kb)
        return True

    if state == "add_spool_name":
        if not text:
            await message.answer("⚠️ Введіть назву котушки:" if u_lang != "en" else "⚠️ Enter spool name:")
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["name"] = text
        user["state"] = "add_spool_type"
        await app.storage.save_user(user)
        auto_type = extract_filament_type_from_name(text)
        await message.answer(
            f"🎨 <b>Оберіть або введіть тип пластику (наприклад: {auto_type}):</b>"
            if u_lang != "en" else
            f"🎨 <b>Select or enter filament type (e.g. {auto_type}):</b>",
            parse_mode=ParseMode.HTML,
        )
        return True

    if state == "add_spool_type":
        if not text:
            await message.answer("⚠️ Введіть тип пластику:" if u_lang != "en" else "⚠️ Enter filament type:")
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["type"] = text.upper()
        user["state"] = "add_spool_grams"
        await app.storage.save_user(user)
        await message.answer(
            "⚖️ <b>Введіть початкову вагу котушки у грамах (наприклад: 1000):</b>"
            if u_lang != "en" else
            "⚖️ <b>Enter spool weight in grams (e.g. 1000):</b>",
            parse_mode=ParseMode.HTML,
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
            )
            return True
        user.setdefault("context_data", {}).setdefault("new_spool", {})["remaining_grams"] = float(val)
        user.setdefault("context_data", {}).setdefault("new_spool", {})["initial_grams"] = float(val)
        user["state"] = "add_spool_price"
        await app.storage.save_user(user)
        await message.answer(
            "💰 <b>Введіть ціну за 1 кг у грн (наприклад: 850):</b>"
            if u_lang != "en" else
            "💰 <b>Enter price per 1 kg in UAH (e.g. 850):</b>",
            parse_mode=ParseMode.HTML,
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
            )
            return True
        pr_val = float(val)
        new_spool = user.get("context_data", {}).get("new_spool", {})
        new_spool["price_per_kg"] = pr_val
        sp_name = new_spool.get("name", "Bambu Spool")
        sp_type = new_spool.get("type", "PLA")
        sp_grams = new_spool.get("remaining_grams", 1000.0)
        init_grams = new_spool.get("initial_grams", sp_grams)

        spools = await app.storage.load_spools()
        new_id = str(uuid.uuid4())
        spools[new_id] = {
            "id": new_id,
            "name": sp_name,
            "type": sp_type,
            "color": "#000000",
            "initial_grams": init_grams,
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
        await message.answer(
            f"✅ <b>Котушку {html.escape(sp_name)} успішно додано на Склад!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool {html.escape(sp_name)} added to warehouse!</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_filament_menu_keyboard(lang=u_lang),
        )
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
            if text in [t1, t2, s_name] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in spools.values():
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s["id"] == text):
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
                    user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                    user["context_data"].pop("mount_spool", None)
                    user["context_data"].pop("mount_printer_id", None)
                    await app.storage.save_user(user)

                    await message.answer(
                        f"✅ <b>Котушку {html.escape(selected['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>"
                        if u_lang != "en" else
                        f"✅ <b>Spool {html.escape(selected['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>",
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
                user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
                user["context_data"].pop("mount_spool", None)
                user["context_data"].pop("mount_printer_id", None)
                await app.storage.save_user(user)

                await message.answer(
                    f"✅ <b>Котушку {html.escape(selected_spool['name'])} встановлено на {html.escape(target_p.name)} [Зовнішній (VT)]!</b>"
                    if u_lang != "en" else
                    f"✅ <b>Spool {html.escape(selected_spool['name'])} mounted on {html.escape(target_p.name)} [External (VT)]!</b>",
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
        user.setdefault("context_data", {})["selected_printer_id"] = target_p.id
        user["context_data"].pop("mount_spool", None)
        user["context_data"].pop("mount_printer_id", None)
        await app.storage.save_user(user)

        await message.answer(
            f"✅ <b>Котушку {html.escape(selected_spool['name'])} встановлено на {html.escape(target_p.name)} [{slot_label}]!</b>"
            if u_lang != "en" else
            f"✅ <b>Spool {html.escape(selected_spool['name'])} mounted on {html.escape(target_p.name)} [{slot_label}]!</b>",
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

            user["state"] = "printer_menu" if target_printer else "idle"
            await app.storage.save_user(user)

            kb = get_single_printer_filament_keyboard(lang=u_lang) if target_printer else get_filament_menu_keyboard(lang=u_lang)
            await message.answer(
                f"✅ <b>Котушку успішно знято та повернуто на Склад!</b>"
                if u_lang != "en" else
                f"✅ <b>Spool successfully unmounted to warehouse!</b>",
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
        selected = None
        for s in spools.values():
            s_name = s.get("name", "Spool")
            s_grams = s.get("remaining_grams", 1000.0)
            s_type = s.get("type", "")
            t1 = f"🧵 {s_name} ({s_grams}g)"
            t2 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            if text in [t1, t2, s_name] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in spools.values():
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s["id"] == text):
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

            card = (
                f"✏️ <b>Редагування котушки: {html.escape(selected.get('name', 'Котушка'))}</b>\n\n"
                f"🏷️ <b>Назва:</b> {html.escape(selected.get('name', ''))}\n"
                f"🎨 <b>Тип:</b> {html.escape(selected.get('type', 'PLA'))}\n"
                f"⚖️ <b>Залишок:</b> {selected.get('remaining_grams', 1000.0)}g\n"
                f"💰 <b>Ціна за 1 кг:</b> {selected.get('price_per_kg', 850.0)} грн"
                f"{assigned_str}\n\n"
                f"Оберіть параметр, який бажаєте змінити:"
                if not is_en else
                f"✏️ <b>Edit Spool: {html.escape(selected.get('name', 'Spool'))}</b>\n\n"
                f"🏷️ <b>Name:</b> {html.escape(selected.get('name', ''))}\n"
                f"🎨 <b>Type:</b> {html.escape(selected.get('type', 'PLA'))}\n"
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
                f"Введіть новий тип пластику (поточний: <b>{html.escape(cur_spool.get('type', 'PLA'))}</b>, наприклад: PLA, PETG, ABS, TPU):"
                if u_lang != "en" else
                f"Enter new material type (current: <b>{html.escape(cur_spool.get('type', 'PLA'))}</b>, e.g. PLA, PETG, ABS, TPU):",
                parse_mode=ParseMode.HTML,
                reply_markup=kb_back,
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

        new_g = float(val)
        target_spool["remaining_grams"] = new_g
        spools[spool_id] = target_spool
        await app.storage.save_spools(spools)

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
        selected = None
        for s in spools.values():
            s_name = s.get("name", "Spool")
            s_grams = s.get("remaining_grams", 1000.0)
            s_type = s.get("type", "")
            t1 = f"🧵 {s_name} ({s_grams}g)"
            t2 = f"🧵 {s_name} ({s_type}, {s_grams}g)"
            if text in [t1, t2, s_name] or text.strip() == s_name.strip():
                selected = s
                break
        if not selected:
            for s in spools.values():
                s_name = s.get("name", "")
                if s_name and (s_name.lower() in text.lower() or text.lower() in s_name.lower() or s["id"] == text):
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
            target_printer.filament_grams = float(val)
            await app.save_printers_config()
            user["state"] = "printer_menu"
            await app.storage.save_user(user)
            await message.answer(
                f"✅ Залишок філаменту для {html.escape(target_printer.name)} змінено на <b>{val}g</b>!"
                if u_lang != "en"
                else f"✅ Filament remaining for {html.escape(target_printer.name)} updated to <b>{val}g</b>!",
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

