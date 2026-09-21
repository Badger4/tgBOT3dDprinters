"""
Edit part handlers.
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
    construct_part_info_keyboard,
    get_part_action_reply_keyboard,
    get_part_editing_reply_keyboard,
    get_parts_inline_keyboard,
)
from bot.states import PartEditingStates
from utils.i18n import get_user_lang
from bot.handlers.parts.view import extract_image_from_message, send_part_info

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["редагувати", "✏️ редагувати", "edit", "✏️ edit", "✏️ редагувати деталь", "редагувати деталь", "✏️ edit part", "edit part"])
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(["редагувати", "✏️ редагувати", "edit", "✏️ edit", "✏️ редагувати деталь", "редагувати деталь", "✏️ edit part", "edit part"])
)
@router.message(
    F.text.lower().in_(["✏️ редагувати деталь", "редагувати деталь", "✏️ edit part", "edit part"])
)
async def handle_edit_part_start(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для редагування.")
        return

    current_state = await state.get_state()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)

    if current_state == PartEditingStates.in_part_info and part_id and part_id in parts:
        part = parts[part_id]
        ikb = construct_part_info_keyboard(part, lang)
        await message.answer(f"✏️ <b>Редагування деталі «{html.escape(part.get('name', 'Деталь'))}»:</b>\nОберіть поле для зміни:", parse_mode=ParseMode.HTML, reply_markup=ikb)
    else:
        await state.set_state(PartEditingStates.select_part_for_edit)
        await message.answer("Оберіть деталь для редагування зі списку нижче:", reply_markup=get_parts_inline_keyboard(parts))


@router.callback_query(F.data.startswith("part_prop_"))
async def handle_click_property(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    prop_name = callback.data.replace("part_prop_", "")
    data = await state.get_data()
    part_id = data.get("selected_part_id")

    # Fallback if state lost: extract part_id from callback message inline keyboard
    if not part_id and callback.message and callback.message.reply_markup:
        for row in callback.message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("part_print_select_"):
                    part_id = btn.callback_data.replace("part_print_select_", "")
                    break

    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if not part_id or part_id not in parts:
        await callback.answer("⚠️ Помилка: деталь не знайдена.", show_alert=True)
        return

    part = parts[part_id]
    draft = data.get("editing_draft") or dict(part)

    await state.set_state(PartEditingStates.property_edit)
    await state.update_data(selected_part_id=part_id, editing_prop=prop_name, editing_draft=draft)

    u_data = await app.storage.load_user(callback.from_user.id)
    lang = get_user_lang(u_data)
    reply_kb = get_part_editing_reply_keyboard(lang)

    await callback.message.answer(
        f"✏️ <b>Введіть/надішліть нове значення для поля <code>{prop_name}</code>:</b>\n"
        f"Після завершення натисніть <b>💾 Зберегти</b> або <b>❌ Скасувати редагування</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb,
    )
    await callback.answer()


@router.message(PartEditingStates.property_edit)
async def process_confirm_property_edit(message: Message, state: FSMContext, app: Any) -> None:
    text = (message.text or "").strip()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)

    data = await state.get_data()
    part_id = data.get("selected_part_id")
    prop_name = data.get("editing_prop")
    draft = data.get("editing_draft") or {}

    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()
    if not part_id or part_id not in parts:
        await message.answer("⚠️ Помилка: деталь не знайдена.")
        await state.clear()
        return

    # Handle SAVE button press
    if text.lower() in ["💾 зберегти", "зберегти", "💾 save", "save"]:
        if draft:
            draft["updated_at"] = time.time()
            parts[part_id] = draft
            await app.storage.save_json(app.storage.parts_file, parts)
            await message.answer("✅ <b>Зміни деталі успішно збережено!</b>", parse_mode=ParseMode.HTML)
        else:
            await message.answer("Збережено!")

        await state.set_state(PartEditingStates.in_part_info)
        await state.update_data(editing_draft=None, editing_prop=None)
        part = parts[part_id]
        text_keyboard = get_part_action_reply_keyboard(lang)
        inline_keyboard = construct_part_info_keyboard(part, lang)

        await send_part_info(message, part, text_keyboard, inline_keyboard)
        return

    # Handle CANCEL EDIT button press
    if text.lower() in ["❌ скасувати редагування", "скасувати редагування", "❌ cancel edit", "cancel edit", "скасувати", "cancel"]:
        await message.answer("❌ <b>Редагування скасовано. Початкові дані збережено.</b>", parse_mode=ParseMode.HTML)
        await state.set_state(PartEditingStates.in_part_info)
        await state.update_data(editing_draft=None, editing_prop=None)
        part = parts[part_id]
        text_keyboard = get_part_action_reply_keyboard(lang)
        inline_keyboard = construct_part_info_keyboard(part, lang)

        await send_part_info(message, part, text_keyboard, inline_keyboard)
        return

    # Apply property edit to draft
    if not draft:
        draft = dict(parts[part_id])

    if prop_name == "name":
        if not text:
            await message.answer("⚠️ <b>Помилка! Назва не може бути порожньою.</b>\nВведіть нову назву деталі:", parse_mode=ParseMode.HTML)
            return
        draft["name"] = text
    elif prop_name == "image":
        if message.document:
            doc = message.document
            mime = str(doc.mime_type or "").lower()
            fname = str(doc.file_name or "").lower()
            if not (mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))):
                await message.answer("⚠️ <b>Помилка! Файл повинен бути зображенням (.jpg, .png, .webp).</b>\nНадішліть фото або введіть '-' для вилучення фото:", parse_mode=ParseMode.HTML)
                return
        if text in ["-", "/skip", "пропустити"]:
            draft["image"] = ""
        else:
            draft["image"] = await extract_image_from_message(message)
    elif prop_name == "count":
        if not text or not text.isdigit():
            await message.answer("⚠️ <b>Помилка! Кількість повинна бути цілим додатним числом (наприклад: 1, 5, 10).</b>\nСпробуйте ще раз:", parse_mode=ParseMode.HTML)
            return
        val = int(text)
        draft["count"] = val
        draft["quantity"] = val
    elif prop_name == "three_mf":
        if message.document:
            doc_name = str(message.document.file_name or "").lower()
            if not doc_name.endswith(".3mf"):
                await message.answer("⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть файл з розширенням .3mf:", parse_mode=ParseMode.HTML)
                return

            doc_id = message.document.file_id
            doc_name_clean = message.document.file_name or "model.3mf"
            draft["three_mf"] = doc_id
            draft["three_mf_name"] = doc_name_clean

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
                if doc_name_clean:
                    clean_doc_name = doc_name_clean.replace("\\", "/").split("/")[-1]
                    (save_dir / clean_doc_name).write_bytes(file_bytes)

                meta = parse_3mf_file(file_bytes, doc_name_clean)
                if meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                    draft["printer_model"] = meta["printer_model"]
                if meta.get("filament_type"):
                    draft["filament_type"] = meta["filament_type"]
                if meta.get("nozzle_diameter"):
                    draft["nozzle_diameter"] = str(meta["nozzle_diameter"])
                if meta.get("weight_g"):
                    try:
                        w_val = float(meta["weight_g"])
                        draft["weight_g"] = w_val
                        draft["weight"] = w_val
                    except (ValueError, TypeError):
                        pass
                if meta.get("time_mins"):
                    try:
                        t_mins = int(meta["time_mins"])
                        draft["time_mins"] = t_mins
                        draft["print_time"] = t_mins
                    except (ValueError, TypeError):
                        pass
            except Exception as e:
                logger.warning(f"Error parsing 3mf in property edit: {e}")
        elif text in ["-", "/skip", "видалити", "видалити файл"]:
            draft["three_mf"] = ""
            draft["three_mf_name"] = ""
            draft["nozzle_diameter"] = "0.4"
            draft["weight_g"] = 0.0
            draft["weight"] = 0.0
            draft["time_mins"] = 0
            draft["print_time"] = 0
        else:
            await message.answer("⚠️ <b>Помилка! Надішліть .3mf файл або '-' для видалення файлу.</b>", parse_mode=ParseMode.HTML)
            return

    await state.update_data(editing_draft=draft)

    inline_keyboard = construct_part_info_keyboard(draft, lang)
    model_info = f" (Модель: {draft.get('printer_model')})" if draft.get('printer_model') and draft.get('printer_model') != 'Unknown' else ""
    await message.answer(
        f"✏️ <b>Чернетку оновлено:</b> {html.escape(draft.get('name', 'Деталь'))}{model_info}\n"
        f"Натисніть <b>💾 Зберегти</b> для підтвердження або <b>❌ Скасувати редагування</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
    )

