"""
Add part wizard handlers.
"""

import html
import time
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from config import logger
from bot.keyboards import get_parts_reply_keyboard
from bot.states import PartCreatingStates, PartEditingStates
from utils.i18n import get_user_lang
from bot.handlers.parts.view import extract_image_from_message, open_parts_list

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_([
        "добавити", "➕ добавити", "додати", "➕ додати", "➕ додати деталь",
        "add", "➕ add", "add part", "➕ нова деталь", "нова деталь", "➕ new part", "new part"
    ])
)
@router.message(
    F.text.lower().in_([
        "добавити", "➕ добавити", "➕ додати деталь", "додати деталь",
        "add part", "➕ нова деталь", "нова деталь", "➕ new part", "new part"
    ])
)
async def handle_add_part_start(message: Message, app: Any, state: FSMContext | None = None) -> None:
    if state:
        await state.set_state(PartCreatingStates.name)
    await message.answer("Введіть назву нової деталі:")


@router.message(PartCreatingStates.name, F.text.lower().in_(["скасувати", "cancel", "❌ скасувати", "назад", "⬅️ назад"]))
@router.message(PartCreatingStates.image, F.text.lower().in_(["скасувати", "cancel", "❌ скасувати", "назад", "⬅️ назад"]))
@router.message(PartCreatingStates.count, F.text.lower().in_(["скасувати", "cancel", "❌ скасувати", "назад", "⬅️ назад"]))
@router.message(PartCreatingStates.three_mf, F.text.lower().in_(["скасувати", "cancel", "❌ скасувати", "назад", "⬅️ назад"]))
async def cancel_add_part(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await message.answer("❌ Створення деталі скасовано.")
    await open_parts_list(message, state, app, lang)


@router.message(PartCreatingStates.name)
async def add_part_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer(
            "⚠️ <b>Помилка! Назва деталі не може бути порожньою.</b>\nБудь ласка, введіть назву деталі:",
            parse_mode=ParseMode.HTML
        )
        return
    await state.update_data(name=name)
    await state.set_state(PartCreatingStates.image)
    await message.answer("Фото (надішліть зображення або введіть '-' щоб пропустити):")


@router.message(PartCreatingStates.image)
async def add_part_image(message: Message, state: FSMContext) -> None:
    if message.document:
        doc = message.document
        mime = str(doc.mime_type or "").lower()
        fname = str(doc.file_name or "").lower()
        if not (mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))):
            await message.answer(
                "⚠️ <b>Помилка! Невірно вказано фото.</b>\nБудь ласка, надішліть файл зображення (.jpg, .png, .webp) або введіть '-' щоб пропустити:",
                parse_mode=ParseMode.HTML
            )
            return

    img_id = await extract_image_from_message(message)
    if message.text and message.text.strip() in ["-", "/skip", "пропустити", "skip"]:
        img_id = ""

    await state.update_data(image=img_id)
    await state.set_state(PartCreatingStates.count)
    await message.answer("Кількість (введіть ціле число, наприклад: 1, 5, 10):")


@router.message(PartCreatingStates.count)
async def add_part_count(message: Message, state: FSMContext) -> None:
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await message.answer(
            "⚠️ <b>Помилка! Кількість повинна бути цілим додатним числом (наприклад: 1, 5, 10).</b>\nСпробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )
        return
    await state.update_data(count=val)
    await state.set_state(PartCreatingStates.three_mf)
    await message.answer(".3mf Файл (надішліть файл моделі або введіть '-' щоб пропустити):")


@router.message(PartCreatingStates.three_mf)
async def add_part_three_mf(message: Message, state: FSMContext, app: Any) -> None:
    if message.document:
        doc_name = str(message.document.file_name or "").lower()
        if not doc_name.endswith(".3mf"):
            await message.answer(
                "⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть файл з розширенням .3mf або введіть '-' для пропуску:",
                parse_mode=ParseMode.HTML
            )
            return
    elif message.text and message.text.strip() not in ["-", "/skip", "пропустити", "skip"]:
        await message.answer(
            "⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть .3mf документ або введіть '-' для пропуску:",
            parse_mode=ParseMode.HTML
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

    if doc_id:
        try:
            file_info = await message.bot.get_file(doc_id)
            file_bytes_io = await message.bot.download_file(file_info.file_path)
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
        except Exception as e:
            logger.warning(f"Error handling 3mf file in add_part_three_mf: {e}")

    parts[part_id] = {
        "id": part_id,
        "name": data.get("name", "Деталь"),
        "image": data.get("image", ""),
        "count": cnt_val,
        "quantity": cnt_val,
        "three_mf": doc_id,
        "three_mf_name": doc_name,
        "old_three_mf": "",
        "printer_model": printer_model,
        "filament_type": filament_type,
        "updated_at": time.time(),
    }

    await app.storage.save_json(app.storage.parts_file, parts)
    await message.answer("✅ <b>Деталь успішно додано!</b>", parse_mode=ParseMode.HTML)

    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)
