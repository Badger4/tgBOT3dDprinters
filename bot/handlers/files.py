"""
3MF and GCode document upload, parsing, compatibility checking, and print job start handlers.
"""

import html
import os

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from bot.keyboards import get_printer_menu_keyboard
from config import STORAGE_DIR, logger
from services.gcode_parser import (
    check_compatibility,
    format_print_time_human,
    get_printer_active_filament,
    parse_3mf_file,
)

router = Router()


@router.message(F.document)
async def handle_document_upload(message: Message, app):
    if not message.document:
        return

    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    if not await app.is_user_approved(chat_id):
        await message.answer("⚠️ У вас немає доступу до бота.")
        return

    doc = message.document
    fname = doc.file_name or "file.3mf"
    if not fname.lower().endswith((".3mf", ".gcode")):
        await message.answer(
            "⚠️ Бот приймає лише файли <b>.3mf</b> та <b>.gcode</b> від Bambu Studio чи OrcaSlicer.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Protection for Pi Zero 512MB RAM: reject files larger than 30MB
    MAX_FILE_SIZE = 30 * 1024 * 1024
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        size_mb = round(doc.file_size / (1024 * 1024), 1)
        await message.answer(
            f"⚠️ Файл занадто великий ({size_mb} MB)! Максимальний розмір для Raspberry Pi — 30 MB.",
            parse_mode=ParseMode.HTML,
        )
        return

    msg_wait = await message.answer(
        f"📥 ⏳ Завантажую та перевіряю 3MF файл: <code>{html.escape(fname)}</code>...", parse_mode=ParseMode.HTML
    )

    try:
        bot_file = await app.bot.get_file(doc.file_id)
        file_bytes_io = await app.bot.download_file(bot_file.file_path)
        content = file_bytes_io.read()

        meta = parse_3mf_file(content, fname)
        if not meta["valid"]:
            await message.answer(f"❌ Помилка файлу: {meta.get('error', 'Невідома')}")
            await msg_wait.delete()
            return

        upload_dir = STORAGE_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = upload_dir / f"{chat_id}_{fname}"
        save_path.write_bytes(content)

        user["context_data"]["pending_file"] = {
            "filename": fname,
            "file_id": doc.file_id,
            "local_filepath": str(save_path),
            "plate_name": meta.get("plate_name", "plate_1.gcode"),
            "printer_model": meta["printer_model"],
            "nozzle_diameter": meta.get("nozzle_diameter", "0.4"),
            "filament_type": meta["filament_type"],
            "tray_info_idx": meta.get("tray_info_idx", ""),
            "filament_color": meta.get("filament_color", ""),
            "filament_name": meta.get("filament_name", ""),
            "weight_g": meta["weight_g"],
            "time_mins": meta["time_mins"],
            "objects": meta.get("objects", []),
        }
        user["state"] = "select_printer_for_file"
        await app.storage.save_user(user)

        noz_str = str(meta.get("nozzle_diameter", "0.4"))
        comp_txt = (
            f"📄 <b>Файл прийнято: {html.escape(fname)}</b>\n"
            f"🖨️ <b>Модель у 3MF файлі:</b> <code>{html.escape(meta['printer_model'])}</code>\n"
            f"🎯 <b>Діаметр сопла:</b> <code>{html.escape(noz_str)} мм</code>\n"
            f"🧵 <b>Тип пластику у файлі:</b> <code>{html.escape(meta['filament_type'])}</code>\n"
            f"⚖️ <b>Необхідно пластику:</b> <b>{meta['weight_g']}g</b>\n"
            f"⏱️ <b>Орієнтовний час друку:</b> <b>{format_print_time_human(meta['time_mins'])}</b>\n"
            f"-----------------------------------\n"
            f"<b>Перевірка сумісності з фермою:</b>\n\n"
        )

        spools_map = await app.storage.load_spools()
        kb_buttons = []
        for p_id, p in app.printers.items():
            active_fil = get_printer_active_filament(p, spools_map)
            c_info = check_compatibility(
                meta["printer_model"],
                meta["filament_type"],
                p.name,
                active_fil,
                printer=p,
                tray_info_idx=meta.get("tray_info_idx", ""),
                color=meta.get("filament_color", ""),
                filament_name=meta.get("filament_name", ""),
                nozzle_diameter=meta.get("nozzle_diameter"),
            )
            if c_info["compatible"]:
                if c_info.get("level") in ["WARNING", "WARN"]:
                    ams_extra = f" [AMS Слот {c_info['matched_ams_slot']}]" if c_info.get("matched_ams_slot") else ""
                    status_str = f"⚠️ Умовно сумісний (Різна модель: {c_info.get('sliced_model', '')} ➔ {c_info.get('target_model', '')}){ams_extra}"
                elif c_info.get("matched_ams_slot"):
                    status_str = f"✅ Сумісний (AMS Слот {c_info['matched_ams_slot']})"
                else:
                    status_str = "✅ Сумісний"
            else:
                if c_info.get("reason_type") == "NOZZLE":
                    status_str = f"🛑 НЕСУМІСНИЙ (Сопло {c_info.get('target_nozzle', '?')}мм vs {c_info.get('sliced_nozzle', '?')}мм)"
                elif c_info.get("reason_type") == "FILAMENT":
                    if c_info.get("target_filament") in ["Не встановлено", "AMS (пластик відсутній)", ""]:
                        status_str = "🛑 НЕСУМІСНИЙ (Пластик не встановлено)"
                    else:
                        status_str = "🛑 НЕСУМІСНИЙ (Пластик)"
                else:
                    status_str = "🛑 НЕСУМІСНИЙ (Різна модель)"

            comp_txt += f"• <b>{html.escape(p.name)}</b>: {status_str}\n"
            if c_info["compatible"]:
                kb_buttons.append([KeyboardButton(text=f"🚀 Запустити на {p.name}")])

        kb_buttons.append([KeyboardButton(text="💰 Розрахувати комерційну вартість 3MF")])
        kb_buttons.append([KeyboardButton(text="⬅️ Назад")])
        reply_kb = ReplyKeyboardMarkup(keyboard=kb_buttons, resize_keyboard=True)

        await message.answer(comp_txt, parse_mode=ParseMode.HTML, reply_markup=reply_kb)
        await msg_wait.delete()
    except Exception as e:
        logger.error(f"Error processing uploaded 3MF document: {e}")
        await message.answer(f"⚠️ Не вдалося обробити файл: {e}")
        await msg_wait.delete()


def format_commercial_card(res: dict, filename: str) -> str:
    pr_g = float(res.get("price_per_g", 0.85))
    p_watt = float(res.get("power_watts", 120.0))
    e_rate = float(res.get("electricity_rate_uah", 4.32))
    return (
        f"<b>💼 Комерційний розрахунок для 3MF</b>\n"
        f"📄 <b>Файл:</b> <code>{html.escape(filename)}</code>\n"
        f"⚖️ <b>Вага:</b> <code>{res['weight_g']}g</code> | ⏱️ <b>Час друку:</b> <code>~{res['time_mins']} хв</code>\n"
        f"📋 <b>Пресет:</b> <b>{html.escape(res['preset_name'])}</b>\n"
        f"-----------------------------------\n"
        f"🧵 <b>Пластик:</b> <code>{res['filament_cost']:.2f} грн</code> <i>({pr_g:.2f} грн/г)</i>\n"
        f"⚡ <b>Електроенергія:</b> <code>{res['electricity_cost']:.2f} грн</code> <i>({p_watt:.0f} Вт, {e_rate:.2f} грн/кВт·год)</i>\n"
        f"🔧 <b>Амортизація:</b> <code>{res['depreciation_cost']:.2f} грн</code> <i>({res['depreciation_str']})</i>\n"
        f"🧼 <b>Витратні матеріали:</b> <code>{res['consumables_cost']:.2f} грн</code> <i>({res['consumables_str']})</i>\n"
        f"-----------------------------------\n"
        f"💵 <b>Собівартість виробу:</b> <code>{res['cost_before_profit']:.2f} грн</code>\n"
        f"💼 <b>Прибуток / Маржа:</b> <code>{res['profit_cost']:.2f} грн</code> <i>({res['profit_str']})</i>\n"
        f"-----------------------------------\n"
        f"💰 <b>ЦІНА ДЛЯ КЛІЄНТА:</b> <code>{res['total_price']:.2f} грн</code>"
    )


@router.message(F.text.lower().in_(["💰 розрахувати комерційну вартість 3mf", "комерційна вартість 3mf"]))
async def handle_calc_3mf_commercial(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    pending_file = user.get("context_data", {}).get("pending_file", {})

    if not pending_file:
        await message.answer("⚠️ Не знайдено завантаженого 3MF файлу. Надішліть файл заново.")
        return

    from bot.handlers.commercial import get_user_presets

    presets = await get_user_presets(app)

    user["state"] = "calc_select_preset_for_3mf"
    await app.storage.save_user(user)

    kb = [[KeyboardButton(text=f"🔹 {p['name']}")] for p in presets.values()]
    kb.append([KeyboardButton(text="📊 Розрахувати для всіх пресетів")])
    kb.append([KeyboardButton(text="⬅️ Назад")])

    await message.answer(
        f"📋 <b>Оберіть комерційний пресет для розрахунку файлу:</b> <code>{html.escape(pending_file.get('filename', '3MF'))}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True),
    )


async def is_3mf_preset_choice_state(message: Message, app) -> bool:
    if not message.text:
        return False
    txt = message.text.strip().lower()
    if txt in ["📊 розрахувати для всіх пресетів", "розрахувати для всіх пресетів"] or message.text.startswith("🔹 "):
        return True
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state", "") == "calc_select_preset_for_3mf"


@router.message(is_3mf_preset_choice_state)
async def handle_3mf_preset_choice(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    text = message.text.strip()

    if text.lower() in ["⬅️ назад", "назад", "скасувати"]:
        user["state"] = "select_printer_for_file"
        await app.storage.save_user(user)
        await message.answer("Повертаюсь до файлу.")
        return True

    pending_file = user.get("context_data", {}).get("pending_file", {})
    if not pending_file:
        await message.answer("⚠️ Не знайдено завантаженого 3MF файлу. Надішліть файл заново.")
        return True

    from bot.handlers.commercial import get_user_presets
    from models.commercial import calculate_commercial_price

    presets = await get_user_presets(app)
    if not presets:
        from bot.handlers.commercial import DEFAULT_PRESETS
        presets = DEFAULT_PRESETS.copy()

    w_g = pending_file.get("weight_g", 0.0)
    t_mins = pending_file.get("time_mins", 0)
    fname = pending_file.get("filename", "3MF")
    file_p_model = pending_file.get("printer_model", "Unknown")
    file_f_type = pending_file.get("filament_type", "PLA")
    file_nozzle = pending_file.get("nozzle_diameter", "0.4")

    # Build keyboard to return back to file options
    spools_map = await app.storage.load_spools()
    kb_buttons = []
    for p_id, p in app.printers.items():
        active_fil = get_printer_active_filament(p, spools_map)
        c_info = check_compatibility(
            file_p_model,
            file_f_type,
            p.name,
            active_fil,
            printer=p,
            tray_info_idx=pending_file.get("tray_info_idx", ""),
            color=pending_file.get("filament_color", ""),
            filament_name=pending_file.get("filament_name", ""),
            nozzle_diameter=file_nozzle,
        )
        if c_info["compatible"]:
            kb_buttons.append([KeyboardButton(text=f"🚀 Запустити на {p.name}")])
    kb_buttons.append([KeyboardButton(text="💰 Розрахувати комерційну вартість 3MF")])
    kb_buttons.append([KeyboardButton(text="⬅️ Назад")])
    file_kb = ReplyKeyboardMarkup(keyboard=kb_buttons, resize_keyboard=True)

    if text == "📊 Розрахувати для всіх пресетів":
        for p in presets.values():
            res = calculate_commercial_price(p, w_g, t_mins)
            w_val = int(w_g) if w_g == int(w_g) else round(w_g, 1)
            inline_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📄 Завантажити розрахунок (PDF)",
                            callback_data=f"comm_quote_pdf_{p['id']}_{w_val}_{int(t_mins)}",
                        )
                    ]
                ]
            )
            await message.answer(
                format_commercial_card(res, fname),
                parse_mode=ParseMode.HTML,
                reply_markup=inline_kb,
            )
    else:
        preset_name_clean = text.replace("🔹 ", "").strip()
        target = next((p for p in presets.values() if p["name"] == preset_name_clean or p["name"] == text), None)
        if not target:
            await message.answer("⚠️ Пресет не знайдено, оберіть зі списку.")
            return True

        res = calculate_commercial_price(target, w_g, t_mins)
        w_val = int(w_g) if w_g == int(w_g) else round(w_g, 1)
        inline_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📄 Завантажити розрахунок (PDF)",
                        callback_data=f"comm_quote_pdf_{target['id']}_{w_val}_{int(t_mins)}",
                    )
                ]
            ]
        )
        await message.answer(
            format_commercial_card(res, fname),
            parse_mode=ParseMode.HTML,
            reply_markup=inline_kb,
        )

    user["state"] = "select_printer_for_file"
    await app.storage.save_user(user)
    return True


@router.message(F.text.startswith("🚀 Запустити на "))
async def handle_select_printer_for_file(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    ctx_data = user.get("context_data", {})
    printer_target_name = message.text.replace("🚀 Запустити на ", "").strip()
    pending_file = ctx_data.get("pending_file", {})
    if not pending_file:
        await message.answer("⚠️ Не знайдено завантаженого файлу. Надішліть .3mf файл знову.")
        return

    target_p = None
    for p in app.printers.values():
        if p.name == printer_target_name:
            target_p = p
            break

    if not target_p:
        await message.answer("⚠️ Принтер не знайдено.")
        return

    sliced_model = pending_file.get("printer_model", "Unknown")
    fil_type = pending_file.get("filament_type", "PLA")
    file_nozzle = pending_file.get("nozzle_diameter", "0.4")
    spools_map = await app.storage.load_spools()
    active_fil = get_printer_active_filament(target_p, spools_map)
    c_info = check_compatibility(
        sliced_model,
        fil_type,
        target_p.name,
        active_fil,
        printer=target_p,
        tray_info_idx=pending_file.get("tray_info_idx", ""),
        color=pending_file.get("filament_color", ""),
        filament_name=pending_file.get("filament_name", ""),
        nozzle_diameter=file_nozzle,
    )
    if not c_info["compatible"]:
        if c_info.get("reason_type") == "NOZZLE":
            s_noz = c_info.get("sliced_nozzle", file_nozzle)
            t_noz = c_info.get("target_nozzle", getattr(target_p, "nozzle_diameter", "0.4"))
            await message.answer(
                f"🚨 <b>ПОМИЛКА СУМІСНОСТІ СОПЛА! ДРУК БЛОКОВАНО!</b>\n\n"
                f"🛑 <b>Невідповідність діаметра сопла!</b>\n"
                f"• <b>Діаметр у файлі (G-code):</b> <code>{html.escape(str(s_noz))} мм</code>\n"
                f"• <b>Сопло на принтері:</b> <code>{html.escape(str(t_noz))} мм</code>\n\n"
                f"<i>Будь ласка, замініть сопло на принтері на {html.escape(str(s_noz))} мм або перенаріжте модель для сопла {html.escape(str(t_noz))} мм.</i>",
                parse_mode=ParseMode.HTML,
            )
        elif c_info.get("reason_type") == "PRINTER":
            await message.answer(
                f"🚨 <b>ПОМИЛКА СУМІСНОСТІ! ДРУК БЛОКОВАНО!</b>\n\n"
                f"🛑 <b>Принтер несумісний з файлом!</b>\n"
                f"• <b>Модель у файлі:</b> <code>{html.escape(str(c_info.get('sliced_model', sliced_model)))}</code>\n"
                f"• <b>Обраний принтер:</b> <code>{html.escape(target_p.name)}</code>\n\n"
                f"<i>Будь ласка, оберіть сумісний принтер або перенаріжте модель для {html.escape(target_p.name)}.</i>",
                parse_mode=ParseMode.HTML,
            )
        else:
            ams_note = ""
            if getattr(target_p, "has_ams", False) and hasattr(target_p, "get_loaded_ams_summary"):
                ams_note = f"\n📋 <b>Заправлені слоти AMS:</b>\n{target_p.get_loaded_ams_summary()}\n"
            await message.answer(
                f"🚨 <b>ПОМИЛКА СУМІСНОСТІ! ДРУК БЛОКОВАНО!</b>\n\n"
                f"🛑 <b>Філамент несумісний з файлом!</b>\n"
                f"• <b>Необхідний пластик:</b> <code>{html.escape(str(c_info.get('sliced_filament', fil_type)))}</code>\n"
                f"• <b>Пластик на принтері:</b> <code>{html.escape(str(c_info.get('target_filament', active_fil or 'Невідомо')))}</code>\n"
                f"{ams_note}\n"
                f"<i>Будь ласка, встановіть відповідний пластик на принтер.</i>",
                parse_mode=ParseMode.HTML,
            )
        return

    w_req = pending_file.get("weight_g", 0.0)
    cost_info = target_p.calculate_job_cost(w_req, pending_file.get("time_mins", 0))

    warn_txt = ""
    if c_info["level"] == "WARNING":
        warn_txt += f"\n{c_info['reason']}\n"

    if w_req > target_p.filament_grams:
        deficit = round(w_req - target_p.filament_grams, 1)
        warn_txt += f"\n⚠️ <b>УВАГА! Недостатньо нитки!</b> Залишок: {target_p.filament_grams}g (Дефіцит: -{deficit}g)\n"

    matched_slot = c_info.get("matched_ams_slot")
    candidate_slots = c_info.get("candidate_ams_slots", [])
    if matched_slot:
        user["context_data"]["selected_ams_slot"] = matched_slot

    user["context_data"]["start_target_pid"] = target_p.id
    user["state"] = "confirm_start_print_job"
    await app.storage.save_user(user)

    confirm_kb_rows = [[KeyboardButton(text=f"✅ Підтвердити старт на {target_p.name}")]]
    if getattr(target_p, "has_ams", False):
        confirm_kb_rows.append([KeyboardButton(text="🎯 Змінити слот AMS"), KeyboardButton(text="⬅️ Назад")])
    else:
        confirm_kb_rows.append([KeyboardButton(text="⬅️ Назад")])
    confirm_kb = ReplyKeyboardMarkup(keyboard=confirm_kb_rows, resize_keyboard=True)

    slot_info_str = ""
    if getattr(target_p, "has_ams", False):
        cur_slot = user["context_data"].get("selected_ams_slot") or matched_slot
        if cur_slot:
            slot_info_str = f"🎯 <b>Подача пластику:</b> AMS Слот {cur_slot} (<code>{html.escape(fil_type)}</code>)\n"
        else:
            slot_info_str = f"🎯 <b>Подача пластику:</b> AMS (Авто-пошук слоту)\n"

        if candidate_slots and len(candidate_slots) > 1:
            slot_info_str += "\n📋 <b>Знайдено декілька слотів AMS з цим пластиком:</b>\n"
            for cs in candidate_slots:
                s_num = cs["slot_num"]
                s_col = cs.get("color", "")
                s_sub = cs.get("sub_brands") or cs.get("tray_info_idx", "")
                is_sel = (s_num == cur_slot)
                tag = " ⭐ <b>[Обрано]</b>" if is_sel else ""
                slot_info_str += f"• <b>Слот {s_num}:</b> {cs['type']} {s_sub} ({s_col}){tag}\n"
            slot_info_str += "<i>(Ви можете змінити слот кнопкою «🎯 Змінити слот AMS» нижче)</i>\n"
    else:
        slot_info_str = f"🧵 <b>Подача пластику:</b> Spool Holder (зовнішній тримач)\n"

    await message.answer(
        f"🚀 <b>Готовність до запуску друку:</b>\n"
        f"📄 <b>Файл:</b> <code>{html.escape(pending_file.get('filename', '3mf'))}</code>\n"
        f"🖨️ <b>Принтер:</b> <b>{html.escape(target_p.name)}</b>\n"
        f"{slot_info_str}"
        f"⚖️ <b>Вага:</b> <b>{w_req}g</b> | ⏱️ <b>Час:</b> ~<b>{pending_file.get('time_mins', 0)} хв</b>\n"
        f"💰 <b>Розрахункова собівартість:</b> <code>{cost_info['total_cost']} грн</code>\n"
        f"{warn_txt}\n"
        f"Натисніть кнопку нижче для запуску:",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb,
    )


@router.message(F.text == "🎯 Змінити слот AMS")
async def handle_change_ams_slot_prompt(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    ctx_data = user.get("context_data", {})
    target_pid = ctx_data.get("start_target_pid")
    target_p = app.printers.get(target_pid) if target_pid else None
    pending_file = ctx_data.get("pending_file", {})

    if not target_p or not getattr(target_p, "has_ams", False):
        await message.answer("⚠️ Цей принтер не підтримує AMS або принтер не обрано.")
        return

    cur_slot = ctx_data.get("selected_ams_slot", 1)
    slot_btns = []
    lines = []
    for s_idx in range(4):
        s_num = s_idx + 1
        t_info = target_p.ams_trays_info.get(str(s_idx), {})
        t_type = t_info.get("type") or "Порожній"
        t_col = t_info.get("color") or ""
        t_sub = t_info.get("sub_brands") or t_info.get("tray_info_idx") or ""
        is_cur = (s_num == cur_slot)
        mark = " ⭐ [Поточний вибір]" if is_cur else ""
        lines.append(f"• <b>Слот {s_num}:</b> {t_type} {t_sub} {t_col}{mark}".strip())
        slot_btns.append(KeyboardButton(text=f"🎯 Обрати Слот {s_num}"))

    user["state"] = "selecting_ams_slot"
    await app.storage.save_user(user)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [slot_btns[0], slot_btns[1]],
            [slot_btns[2], slot_btns[3]],
            [KeyboardButton(text="⬅️ Назад до підтвердження")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        f"🎨 <b>Оберіть слот AMS для друку файлу</b> <code>{html.escape(pending_file.get('filename', '3mf'))}</code>:\n\n"
        + "\n".join(lines)
        + "\n\n<i>Натисніть на слот, з якого принтер повинен забирати нитку:</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(F.text.startswith("🎯 Обрати Слот "))
async def handle_ams_slot_chosen(message: Message, app):
    import re
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    ctx_data = user.get("context_data", {})
    target_pid = ctx_data.get("start_target_pid")
    target_p = app.printers.get(target_pid) if target_pid else None
    pending_file = ctx_data.get("pending_file", {})

    if not target_p:
        await message.answer("⚠️ Принтер не обрано.")
        return

    m = re.search(r"\b([1-4])\b", message.text)
    if m:
        chosen_slot = int(m.group(1))
        ctx_data["selected_ams_slot"] = chosen_slot
    else:
        chosen_slot = ctx_data.get("selected_ams_slot", 1)

    user["state"] = "confirm_start_print_job"
    await app.storage.save_user(user)

    t_info = target_p.ams_trays_info.get(str(chosen_slot - 1), {})
    t_type = t_info.get("type") or "Пластик"
    t_col = t_info.get("color") or ""
    t_sub = t_info.get("sub_brands") or t_info.get("tray_info_idx") or ""

    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"✅ Підтвердити старт на {target_p.name}")],
            [KeyboardButton(text="🎯 Змінити слот AMS"), KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        f"✅ <b>Встановлено слот подачі:</b> <b>AMS Слот {chosen_slot}</b> ({t_type} {t_sub} {t_col})\n\n"
        f"Тепер натисніть кнопку нижче для запуску друку:",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb,
    )


@router.message(F.text == "⬅️ Назад до підтвердження")
async def handle_back_to_confirm(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    ctx_data = user.get("context_data", {})
    target_pid = ctx_data.get("start_target_pid")
    target_p = app.printers.get(target_pid) if target_pid else None

    if not target_p:
        await message.answer("⚠️ Принтер не обрано.")
        return

    user["state"] = "confirm_start_print_job"
    await app.storage.save_user(user)

    confirm_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"✅ Підтвердити старт на {target_p.name}")],
            [KeyboardButton(text="🎯 Змінити слот AMS"), KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )

    cur_slot = ctx_data.get("selected_ams_slot", 1)
    await message.answer(
        f"Повертаємось до запуску друку на <b>{html.escape(target_p.name)}</b> (обрано AMS Слот {cur_slot}).",
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb,
    )


@router.message(F.text.startswith("✅ Підтвердити старт на "))
async def handle_confirm_start_print_job(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    ctx_data = user.get("context_data", {})
    target_pid = ctx_data.get("start_target_pid")
    target_p = app.printers.get(target_pid) if target_pid else None
    pending_file = ctx_data.get("pending_file", {})

    if target_p and pending_file:
        local_path = pending_file.get("local_filepath")
        fname = pending_file.get("filename", "print.3mf")
        plate_name = pending_file.get("plate_name", "plate_1.gcode")
        file_bytes = None

        if local_path and os.path.exists(local_path):
            try:
                with open(local_path, "rb") as f:
                    file_bytes = f.read()
            except Exception as e:
                logger.error(f"Error reading local file {local_path}: {e}")

        if not file_bytes and pending_file.get("file_id") and app.bot:
            try:
                bot_file = await app.bot.get_file(pending_file["file_id"])
                file_bytes_io = await app.bot.download_file(bot_file.file_path)
                file_bytes = file_bytes_io.read()
            except Exception as e:
                logger.error(f"Error re-downloading file from Telegram: {e}")

        if not file_bytes:
            await message.answer("⚠️ Не вдалося прочитати файл для відправки на принтер. Надішліть файл ще раз.")
            return

        msg_wait = await message.answer(
            f"🚀 ⏳ Завантажую <code>{html.escape(fname)}</code> на принтер <b>{html.escape(target_p.name)}</b> по FTPS та запускаю друк...",
            parse_mode=ParseMode.HTML,
        )

        chosen_slot = ctx_data.get("selected_ams_slot")
        w_req = float(pending_file.get("weight_g", 0.0) or 0.0)
        success, print_msg = await target_p.start_print_job_async(
            file_bytes, fname, plate_name=plate_name, ams_slot=chosen_slot, weight_g=w_req
        )

        if success:
            await app.save_printers_config()

            user["state"] = "printer_menu"
            user["context_data"]["selected_printer_id"] = target_p.id
            await app.storage.save_user(user)

            used_slot_key = getattr(target_p, "_current_job_slot_key", None) or target_p.get_active_slot_key()
            rem_g = target_p.get_slot_grams(used_slot_key)
            if used_slot_key == "254":
                slot_label = "Зовнішній тримач (External)"
            elif str(used_slot_key).isdigit() and int(used_slot_key) < 4:
                slot_label = f"AMS Слот {int(used_slot_key) + 1}"
            else:
                slot_label = f"Слот {used_slot_key}"

            await message.answer(
                f"{print_msg}\n"
                f"📦 Новий залишок нитки ({slot_label}): <b>{rem_g}g</b>\n\n"
                f"Х-хмпф! Друк відправлено! І тільки спробуй за ним не стежити, Бака! 😤💅",
                parse_mode=ParseMode.HTML,
                reply_markup=get_printer_menu_keyboard(target_p),
            )
        else:
            await message.answer(f"🛑 <b>ПОМИЛКА ЗАПУСКУ ДРУКУ!</b>\n{print_msg}", parse_mode=ParseMode.HTML)

        try:
            await msg_wait.delete()
        except Exception:
            pass
