"""
Add part wizard handlers.
"""

import html
import time
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from config import logger
from bot.keyboards import (
    get_main_keyboard,
    get_part_cancel_inline_keyboard,
    get_part_creation_reply_keyboard,
    get_parts_reply_keyboard,
)
from bot.states import PartCreatingStates, PartEditingStates
from utils.i18n import get_user_lang, t
from bot.handlers.parts.view import extract_image_from_message, open_parts_list

router = Router()

CANCEL_TEXTS = [
    "скасувати", "cancel", "❌ скасувати", "❌ cancel",
    "назад", "⬅️ назад", "back", "⬅️ back",
    "відміна", "відмінити", "/cancel",
]

MAIN_MENU_TEXTS = [
    "головне меню", "main menu", "меню", "menu", "🏠 головне меню", "🏠 main menu",
    "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню",
]

NAVIGATION_CANCEL_TEXTS = [
    "📦 склад", "склад", "📦 warehouse", "warehouse", "📦 склад котушок", "склад котушок",
    "🧵 філамент & ams", "філамент & ams", "🧵 філамент", "філамент", "🧵 filament", "filament",
    "🖨️ принтери", "принтери", "🖨️ printers", "printers",
    "📊 стан ферми", "стан ферми", "📊 farm status", "farm status", "ферма",
    "🧩 склад деталей", "склад деталей", "🧩 parts stock", "parts stock",
    "➕ додати котушку", "додати котушку", "➕ додати", "додати", "➕ add spool", "add spool",
    "/start", "/menu", "/printers", "/warehouse", "/farm",
]


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_([
        "добавити", "➕ добавити", "➕ додати деталь", "додати деталь",
        "➕ добавити деталь", "добавити деталь",
        "add", "➕ add", "add part", "➕ add part", "➕ нова деталь", "нова деталь", "➕ new part", "new part"
    ])
)
@router.message(
    F.text.lower().in_([
        "добавити", "➕ добавити", "➕ додати деталь", "додати деталь",
        "➕ добавити деталь", "добавити деталь",
        "add part", "➕ add part", "➕ нова деталь", "нова деталь", "➕ new part", "new part"
    ])
)
async def handle_add_part_start(message: Message, app: Any, state: FSMContext | None = None) -> None:
    if state:
        await state.set_state(PartCreatingStates.name)
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    reply_kb = get_part_creation_reply_keyboard(lang, allow_skip=False)
    await message.answer(
        "➕ <b>Додавання нової деталі</b>\n\nВведіть назву нової деталі:" if lang != "en" else "➕ <b>Add new part</b>\n\nEnter new part name:",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb,
    )


@router.message(PartCreatingStates.name, F.text.lower().in_(NAVIGATION_CANCEL_TEXTS))
@router.message(PartCreatingStates.image, F.text.lower().in_(NAVIGATION_CANCEL_TEXTS))
@router.message(PartCreatingStates.count, F.text.lower().in_(NAVIGATION_CANCEL_TEXTS))
@router.message(PartCreatingStates.three_mf, F.text.lower().in_(NAVIGATION_CANCEL_TEXTS))
async def cancel_add_part_and_navigate(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    text_low = (message.text or "").strip().lower()

    await message.answer("❌ Створення деталі скасовано." if lang != "en" else "❌ Part creation cancelled.")

    if text_low in ["➕ додати котушку", "додати котушку", "➕ додати", "додати", "➕ add spool", "add spool"]:
        from bot.handlers.filament.add import handle_add_spool_start
        await handle_add_spool_start(message, app, state)
    elif text_low in [
        "📦 склад", "склад", "📦 warehouse", "warehouse", "📦 склад котушок", "склад котушок",
        "🧵 філамент & ams", "філамент & ams", "🧵 філамент", "філамент", "🧵 filament", "filament"
    ]:
        from bot.handlers.filament.view import handle_filament_menu
        await handle_filament_menu(message, app, state)
    elif text_low in ["🖨️ принтери", "принтери", "🖨️ printers", "printers"]:
        from bot.handlers.printers.view import handle_list_printers
        await handle_list_printers(message, app, state)
    elif text_low in ["📊 стан ферми", "стан ферми", "📊 farm status", "farm status", "ферма"]:
        from bot.handlers.dashboard import handle_dashboard
        await handle_dashboard(message, app, state)
    elif text_low in ["🧩 склад деталей", "склад деталей", "🧩 parts stock", "parts stock"]:
        await open_parts_list(message, state, app, lang)
    elif text_low in ["/start"]:
        from bot.handlers.start import cmd_start
        await cmd_start(message, app, state)
    else:
        is_admin = await app.is_user_admin(str(message.from_user.id)) if (app and message.from_user) else False
        await message.answer(
            "🤖 *Головне меню 3D Ферми*\nОбирай розділ або відкривай WebApp! 🚀" if lang != "en" else "🤖 *3D Farm Main Menu*\nSelect a section or open WebApp! 🚀",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(is_admin, lang),
        )


@router.message(PartCreatingStates.name, F.text.lower().in_(MAIN_MENU_TEXTS))
@router.message(PartCreatingStates.image, F.text.lower().in_(MAIN_MENU_TEXTS))
@router.message(PartCreatingStates.count, F.text.lower().in_(MAIN_MENU_TEXTS))
@router.message(PartCreatingStates.three_mf, F.text.lower().in_(MAIN_MENU_TEXTS))
async def cancel_add_part_main_menu(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    is_admin = await app.is_user_admin(str(message.from_user.id)) if (app and message.from_user) else False
    await message.answer(
        "❌ Створення деталі скасовано." if lang != "en" else "❌ Part creation cancelled.",
        reply_markup=get_main_keyboard(is_admin, lang),
    )


@router.message(PartCreatingStates.name, F.text.lower().in_(CANCEL_TEXTS))
@router.message(PartCreatingStates.image, F.text.lower().in_(CANCEL_TEXTS))
@router.message(PartCreatingStates.count, F.text.lower().in_(CANCEL_TEXTS))
@router.message(PartCreatingStates.three_mf, F.text.lower().in_(CANCEL_TEXTS))
async def cancel_add_part(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    await message.answer("❌ Створення деталі скасовано." if lang != "en" else "❌ Part creation cancelled.")
    await open_parts_list(message, state, app, lang)


@router.callback_query(F.data == "cancel_part_creation")
async def handle_cancel_part_callback(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    u_data = await app.storage.load_user(callback.from_user.id) if (app and callback.from_user) else None
    lang = get_user_lang(u_data)
    await callback.answer("Скасовано" if lang != "en" else "Cancelled")
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ Створення деталі скасовано." if lang != "en" else "❌ Part creation cancelled.")
        await open_parts_list(callback.message, state, app, lang)


@router.callback_query(F.data == "skip_part_step")
async def handle_skip_part_callback(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    await callback.answer()
    cur_state = await state.get_state()
    u_data = await app.storage.load_user(callback.from_user.id) if (app and callback.from_user) else None
    lang = get_user_lang(u_data)
    if cur_state == PartCreatingStates.image:
        await state.update_data(image="")
        await state.set_state(PartCreatingStates.count)
        if callback.message:
            await callback.message.answer(
                "Кількість (введіть ціле число, наприклад: 1, 5, 10):" if lang != "en" else "Quantity (enter integer, e.g. 1, 5, 10):",
                reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=False),
            )
    elif cur_state == PartCreatingStates.three_mf:
        data = await state.get_data()
        part_id = f"part_{int(time.time() * 1000)}"
        parts: dict[str, dict[str, Any]] = await app.storage.load_parts()
        try:
            cnt_val = int(data.get("count", 0))
        except (ValueError, TypeError):
            cnt_val = 0
        parts[part_id] = {
            "id": part_id,
            "name": data.get("name", "Деталь"),
            "image": data.get("image", ""),
            "count": cnt_val,
            "quantity": cnt_val,
            "three_mf": "",
            "three_mf_name": "",
            "old_three_mf": "",
            "printer_model": "Unknown",
            "filament_type": "PLA",
            "updated_at": time.time(),
        }
        await app.storage.save_json(app.storage.parts_file, parts)
        if callback.message:
            await callback.message.answer("✅ <b>Деталь успішно додано!</b>", parse_mode=ParseMode.HTML)
            await open_parts_list(callback.message, state, app, lang)


@router.message(PartCreatingStates.name)
async def add_part_name(message: Message, state: FSMContext, app: Any = None) -> None:
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer(
            "⚠️ <b>Помилка! Назва деталі не може бути порожньою.</b>\nБудь ласка, введіть назву деталі:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=False),
        )
        return
    await state.update_data(name=name)
    await state.set_state(PartCreatingStates.image)
    reply_kb = get_part_creation_reply_keyboard(lang, allow_skip=True)
    await message.answer(
        "Фото (надішліть зображення або введіть '-' щоб пропустити):" if lang != "en" else "Photo (send image or enter '-' to skip):",
        reply_markup=reply_kb,
    )


@router.message(PartCreatingStates.image)
async def add_part_image(message: Message, state: FSMContext, app: Any = None) -> None:
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    text_val = (message.text or "").strip().lower()

    if message.document:
        doc = message.document
        mime = str(doc.mime_type or "").lower()
        fname = str(doc.file_name or "").lower()
        if not (mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))):
            await message.answer(
                "⚠️ <b>Помилка! Невірно вказано фото.</b>\nБудь ласка, надішліть файл зображення (.jpg, .png, .webp) або введіть '-' щоб пропустити:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=True),
            )
            return

    img_id = await extract_image_from_message(message)
    if text_val in ["-", "/skip", "пропустити", "skip", "⏩ пропустити", "⏩ skip"]:
        img_id = ""

    await state.update_data(image=img_id)
    await state.set_state(PartCreatingStates.count)
    reply_kb = get_part_creation_reply_keyboard(lang, allow_skip=False)
    await message.answer(
        "Кількість (введіть ціле число, наприклад: 1, 5, 10):" if lang != "en" else "Quantity (enter integer, e.g. 1, 5, 10):",
        reply_markup=reply_kb,
    )


@router.message(PartCreatingStates.count)
async def add_part_count(message: Message, state: FSMContext, app: Any = None) -> None:
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await message.answer(
            "⚠️ <b>Помилка! Кількість повинна бути цілим додатним числом (наприклад: 1, 5, 10).</b>\nСпробуйте ще раз:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=False),
        )
        return
    await state.update_data(count=val)
    await state.set_state(PartCreatingStates.three_mf)
    reply_kb = get_part_creation_reply_keyboard(lang, allow_skip=True)
    await message.answer(
        ".3mf Файл (надішліть файл моделі або введіть '-' щоб пропустити):" if lang != "en" else ".3mf File (send model file or enter '-' to skip):",
        reply_markup=reply_kb,
    )


@router.message(PartCreatingStates.three_mf)
async def add_part_three_mf(message: Message, state: FSMContext, app: Any) -> None:
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    text_val = (message.text or "").strip().lower()

    if message.document:
        doc_name = str(message.document.file_name or "").lower()
        if not doc_name.endswith(".3mf"):
            await message.answer(
                "⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть файл з розширенням .3mf або введіть '-' для пропуску:",
                parse_mode=ParseMode.HTML,
                reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=True),
            )
            return
    elif text_val not in ["-", "/skip", "пропустити", "skip", "⏩ пропустити", "⏩ skip"]:
        await message.answer(
            "⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть .3mf документ або введіть '-' для пропуску:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_part_creation_reply_keyboard(lang, allow_skip=True),
        )
        return


    data = await state.get_data()
    doc_id = message.document.file_id if message.document else ""
    doc_name = message.document.file_name if message.document else "model.3mf"

    part_id = f"part_{int(time.time() * 1000)}"
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    try:
        cnt_val = int(data.get("count", 0))
    except (ValueError, TypeError):
        cnt_val = 0

    printer_model = "Unknown"
    filament_type = "PLA"
    nozzle_diameter = "0.4"
    weight_g = 0.0
    time_mins = 0

    if doc_id:
        try:
            bot_instance = message.bot or getattr(app, "bot", None)
            if bot_instance:
                file_info = await bot_instance.get_file(doc_id)
                file_bytes_io = await bot_instance.download_file(file_info.file_path)
                file_bytes = file_bytes_io.read()

            import config
            from services.gcode_parser import parse_3mf_file
            save_dir = config.STORAGE_DIR / "uploads"
            save_dir.mkdir(parents=True, exist_ok=True)
            (save_dir / doc_id).write_bytes(file_bytes)
            if doc_name:
                clean_doc_name = doc_name.replace("\\", "/").split("/")[-1]
                (save_dir / clean_doc_name).write_bytes(file_bytes)

            meta = parse_3mf_file(file_bytes, doc_name)
            if meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                printer_model = meta["printer_model"]
            if meta.get("filament_type"):
                filament_type = meta["filament_type"]
            if meta.get("nozzle_diameter"):
                nozzle_diameter = str(meta["nozzle_diameter"])
            if meta.get("weight_g"):
                try:
                    weight_g = float(meta["weight_g"])
                except (ValueError, TypeError):
                    weight_g = 0.0
            if meta.get("time_mins"):
                try:
                    time_mins = int(meta["time_mins"])
                except (ValueError, TypeError):
                    time_mins = 0
        except Exception as e:
            logger.warning(f"Error handling 3mf file in add_part_three_mf: {e}")

    parts[part_id] = {
        "id": part_id,
        "name": data.get("name", "Деталь"),
        "image": data.get("image", ""),
        "count": cnt_val,
        "quantity": cnt_val,
        "three_mf": doc_id,
        "three_mf_name": doc_name if doc_id else "",
        "old_three_mf": "",
        "printer_model": printer_model,
        "filament_type": filament_type,
        "nozzle_diameter": nozzle_diameter,
        "weight_g": weight_g,
        "weight": weight_g,
        "time_mins": time_mins,
        "print_time": time_mins,
        "updated_at": time.time(),
    }

    await app.storage.save_json(app.storage.parts_file, parts)

    success_text = "✅ <b>Деталь успішно додано!</b>"
    details = []
    if printer_model and printer_model != "Unknown":
        details.append(f"🖨️ {html.escape(printer_model)}")
    if filament_type:
        details.append(f"🧵 {html.escape(filament_type)}")
    if weight_g > 0:
        details.append(f"⚖️ {weight_g:.1f} г")
    if time_mins > 0:
        from services.gcode_parser import format_print_time_human
        details.append(f"⏱️ {format_print_time_human(time_mins)}")
    if details:
        success_text += "\nℹ️ " + " | ".join(details)

    await message.answer(success_text, parse_mode=ParseMode.HTML)

    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)
