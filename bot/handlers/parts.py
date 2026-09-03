"""
Parts warehouse management handlers for Telegram Bot matching reference bot 3D parts structure.
"""

import html
import time
from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from config import logger

from bot.keyboards import (
    construct_part_info_keyboard,
    get_main_keyboard,
    get_part_action_reply_keyboard,
    get_part_editing_reply_keyboard,
    get_parts_inline_keyboard,
    get_parts_reply_keyboard,
    get_printer_select_inline_keyboard,
)
from bot.states import PartCreatingStates, PartEditingStates
from utils.i18n import get_user_lang, t

router = Router()


async def open_parts_list(message: Message, state: FSMContext, app: Any, lang: str = "uk") -> None:
    await state.set_state(PartEditingStates.in_parts_list)
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    text_keyboard = get_parts_reply_keyboard(lang)
    inline_keyboard = get_parts_inline_keyboard(parts)

    await message.answer(".", reply_markup=text_keyboard)
    if not parts:
        await message.answer(
            "🧩 <b>Склад деталей порожній!</b>\nНатисніть <b>Добавити</b>, щоб додати першу деталь.",
            parse_mode=ParseMode.HTML,
            reply_markup=inline_keyboard,
        )
    else:
        await message.answer("Список деталей:", reply_markup=inline_keyboard)


@router.message(F.text.in_(["🧩 Склад деталей", "🧩 Parts Stock", "Склад деталей", "3Д"]))
async def handle_parts_warehouse_btn(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)


async def extract_image_from_message(message: Message) -> str:
    """Extracts Telegram photo file_id or downloads PNG/JPEG/WEBP image document to uploads with compression."""
    if message.photo:
        try:
            import config
            import time
            file_info = await message.bot.get_file(message.photo[-1].file_id)
            file_bytes_io = await message.bot.download_file(file_info.file_path)
            file_bytes = file_bytes_io.read()

            from utils.image_utils import compress_part_photo
            compressed = compress_part_photo(file_bytes)

            file_token = f"img_{int(time.time())}_{message.photo[-1].file_id[:10]}.jpg"
            upload_dir = config.STORAGE_DIR / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            save_path = upload_dir / file_token
            save_path.write_bytes(compressed)
            return f"/uploads/{file_token}"
        except Exception as e:
            logger.warning(f"Error compressing photo message: {e}")
            return message.photo[-1].file_id

    if message.document:
        doc = message.document
        mime = str(doc.mime_type or "").lower()
        fname = str(doc.file_name or "").lower()
        if mime.startswith("image/") or fname.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            try:
                import config
                import re
                import time
                file_info = await message.bot.get_file(doc.file_id)
                file_bytes_io = await message.bot.download_file(file_info.file_path)
                file_bytes = file_bytes_io.read()

                from utils.image_utils import compress_part_photo
                compressed = compress_part_photo(file_bytes)

                clean_fname = re.sub(r"[^a-zA-Z0-9_]", "_", doc.file_name.rsplit(".", 1)[0] if doc.file_name else "image")
                file_token = f"img_{int(time.time())}_{clean_fname}.jpg"

                upload_dir = config.STORAGE_DIR / "uploads"
                upload_dir.mkdir(parents=True, exist_ok=True)
                save_path = upload_dir / file_token
                save_path.write_bytes(compressed)

                return f"/uploads/{file_token}"
            except Exception as e:
                logger.warning(f"Error downloading image document: {e}")
                return doc.file_id

    if message.text:
        return message.text.strip()

    return ""


async def send_part_info(target_message: Message, part: dict[str, Any], text_keyboard: ReplyKeyboardMarkup, inline_keyboard: InlineKeyboardMarkup) -> None:
    await target_message.answer(".", reply_markup=text_keyboard)

    img = str(part.get("image", "") or "").strip()
    name = html.escape(part.get("name", "Деталь"))
    p_model = part.get("printer_model")
    model_para = f"\n🖨️ <b>Принтер:</b> {html.escape(p_model)}" if p_model and p_model != "Unknown" else ""
    cnt = part.get("count", part.get("quantity", 0))
    caption_text = f"🧩 <b>{name}</b>{model_para}\n📦 <b>Кількість:</b> {cnt} шт"

    photo_sent = False
    if img:
        try:
            if img.startswith("http://") or img.startswith("https://") or (len(img) > 15 and "/" not in img and "\\" not in img):
                await target_message.answer_photo(photo=img, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                photo_sent = True
            else:
                import config
                from aiogram.types import FSInputFile
                img_file_name = Path(img).name
                p = config.STORAGE_DIR / "uploads" / img_file_name
                if not p.exists():
                    p = Path(img)
                if not p.exists():
                    p = config.STORAGE_DIR / img
                if p.exists():
                    await target_message.answer_photo(photo=FSInputFile(p), caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                    photo_sent = True
        except Exception as e:
            logger.warning(f"Error sending photo [{img}]: {e}")

    if not photo_sent:
        await target_message.answer(caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)


@router.callback_query(F.data.startswith("part_view_"))
async def handle_select_part_view(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    part_id = callback.data.replace("part_view_", "")
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if part_id not in parts:
        await callback.answer("⚠️ Деталь не знайдено!", show_alert=True)
        return

    part = parts[part_id]
    await state.set_state(PartEditingStates.in_part_info)
    await state.update_data(selected_part_id=part_id)

    u_data = await app.storage.load_user(callback.from_user.id)
    lang = get_user_lang(u_data)

    text_keyboard = get_part_action_reply_keyboard(lang)
    inline_keyboard = construct_part_info_keyboard(part, lang)

    await send_part_info(callback.message, part, text_keyboard, inline_keyboard)

    three_mf = part.get("three_mf")
    if three_mf:
        await callback.message.answer(".3mf:")
        try:
            await callback.message.answer_document(three_mf)
        except Exception as e:
            await callback.message.answer(f"Помилка відправки файлу: {e}")

    await callback.answer()


@router.callback_query(F.data.startswith("part_print_select_"))
async def handle_part_print_select(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    part_id = callback.data.replace("part_print_select_", "")
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if part_id not in parts:
        await callback.answer("⚠️ Деталь не знайдено!", show_alert=True)
        return

    part = parts[part_id]
    three_mf = part.get("three_mf")

    if not three_mf:
        await callback.answer("⚠️ Для цієї деталі ще не завантажено файл .3mf!", show_alert=True)
        return

    if not app.printers:
        await callback.answer("⚠️ Немає підключених принтерів у фермі!", show_alert=True)
        return

    u_data = await app.storage.load_user(callback.from_user.id)
    lang = get_user_lang(u_data)

    kb = get_printer_select_inline_keyboard(part_id, app.printers, part, lang)
    model_str = f"\n🖨️ <b>Модель у файлі:</b> {html.escape(part.get('printer_model'))}" if part.get('printer_model') and part.get('printer_model') != 'Unknown' else ""

    await callback.message.answer(
        f"🚀 Оберіть принтер для відправки та запуску друку деталі <b>{html.escape(part.get('name', 'Деталь'))}</b>{model_str}:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("part_exec_print"))
async def handle_part_exec_print(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    raw = callback.data.replace("part_exec_print_", "").replace("part_exec_print:", "")
    if ":" in raw:
        data_parts = raw.split(":", 1)
    else:
        data_parts = raw.rsplit("_", 1)

    if len(data_parts) < 2:
        await callback.answer("⚠️ Невірний формат команди", show_alert=True)
        return

    part_id, printer_id = data_parts[0], data_parts[1]
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()
    printer = app.printers.get(printer_id)

    if part_id not in parts:
        await callback.answer("⚠️ Деталь не знайдено!", show_alert=True)
        return

    if not printer:
        await callback.answer("⚠️ Обраний принтер недоступний!", show_alert=True)
        return

    part = parts[part_id]
    three_mf_id = part.get("three_mf")

    if not three_mf_id:
        await callback.answer("⚠️ У деталі відсутній файл .3mf!", show_alert=True)
        return

    # Check compatibility
    from services.gcode_parser import check_compatibility, get_printer_active_filament
    app_ref = getattr(callback.bot, "_app_ref", None)
    spools_map = await app_ref.storage.load_spools() if app_ref and hasattr(app_ref, "storage") else None
    active_fil = get_printer_active_filament(printer, spools_map)
    comp = check_compatibility(part.get("printer_model", ""), part.get("filament_type", ""), printer.name, active_fil)
    if not comp.get("compatible"):
        reason = comp.get("reason", "🛑 Несумісний принтер або пластик!")
        await callback.answer(f"🛑 ДРУК БЛОКОВАНО: {reason}", show_alert=True)
        await callback.message.answer(
            f"🚨 <b>ПОМИЛКА СУМІСНОСТІ! ДРУК БЛОКОВАНО!</b>\n\n{reason}\n\n"
            f"Необхідний пластик: <code>{html.escape(part.get('filament_type', 'Невідомо'))}</code>\n"
            f"Пластик на принтері: <code>{html.escape(active_fil or 'Невідомо')}</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    await callback.answer("⏳ Завантаження .3mf файлу та відправка на принтер...")

    try:
        import config
        from pathlib import Path
        clean_name = three_mf_id.replace("\\", "/").split("/")[-1]
        clean_rel = three_mf_id.lstrip("/").lstrip("\\")

        possible_paths = [
            config.STORAGE_DIR / "uploads" / clean_name,
            config.STORAGE_DIR / "parts_files" / clean_name,
            config.STORAGE_DIR / clean_name,
            config.STORAGE_DIR / clean_rel,
            Path(three_mf_id),
        ]

        file_bytes = None
        for p in possible_paths:
            try:
                if p.exists() and p.is_file():
                    file_bytes = p.read_bytes()
                    break
            except Exception:
                pass

        if not file_bytes:
            # Check if three_mf_id is a genuine Telegram file_id (no dots, no slashes, length > 20)
            is_file_id = bool(
                three_mf_id
                and not three_mf_id.startswith(("/", "\\", "http://", "https://"))
                and "." not in three_mf_id
                and "/" not in three_mf_id
                and "\\" not in three_mf_id
                and len(three_mf_id) >= 20
            )
            if is_file_id:
                try:
                    bot = callback.bot
                    file_info = await bot.get_file(three_mf_id)
                    file_bytes_io = await bot.download_file(file_info.file_path)
                    file_bytes = file_bytes_io.read()
                except Exception as e_dl:
                    logger.warning(f"Error downloading file_id {three_mf_id} from Telegram: {e_dl}")

        if not file_bytes:
            await callback.message.answer("⚠️ <b>Помилка:</b> Файл .3mf не знайдено на сервері. Надішліть новий .3mf файл у меню деталі.", parse_mode=ParseMode.HTML)
            return

        filename = part.get("three_mf_name") or f"{part.get('name', 'model')}.3mf"
        part_title = part.get("name") or filename

        ok, msg = await printer.start_print_job_async(file_bytes, filename, part_name=part_title)
        if ok:
            printer._is_printing = True
            printer._was_running = True
            printer._job_started_from_app = True
            comp_warning = f"\n\n{comp['reason']}" if comp.get("reason") and not comp.get("compatible") else ""
            await callback.message.answer(
                f"🚀 <b>Друк успішно запущено!</b>\nДеталь: <b>{html.escape(part.get('name', 'Деталь'))}</b>\nПринтер: <b>{html.escape(printer.name)}</b>{comp_warning}",
                parse_mode=ParseMode.HTML,
            )
        else:
            await callback.message.answer(f"⚠️ Помилка запуску друку: {msg}")
    except Exception as e:
        await callback.message.answer(f"⚠️ Помилка отримання або відправки файлу: {e}")


@router.callback_query(F.data.startswith("part_prop_"), PartEditingStates.in_part_info)
async def handle_click_property(callback: CallbackQuery, state: FSMContext, app: Any) -> None:
    prop_name = callback.data.replace("part_prop_", "")
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if not part_id or part_id not in parts:
        await callback.answer("⚠️ Помилка: деталь не знайдена.", show_alert=True)
        return

    part = parts[part_id]
    draft = data.get("editing_draft") or dict(part)

    await state.set_state(PartEditingStates.property_edit)
    await state.update_data(editing_prop=prop_name, editing_draft=draft)

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
    if text in ["💾 Зберегти", "💾 Save"]:
        if draft:
            draft["updated_at"] = time.time()
            parts[part_id] = draft
            await app.storage.save_json(app.storage.parts_file, parts)
            await message.answer("✅ <b>Зміни деталі успішно збережено!</b>", parse_mode=ParseMode.HTML)
        else:
            await message.answer("Збережено!")

        await state.set_state(PartEditingStates.in_part_info)
        part = parts[part_id]
        text_keyboard = get_part_action_reply_keyboard(lang)
        inline_keyboard = construct_part_info_keyboard(part, lang)

        await send_part_info(message, part, text_keyboard, inline_keyboard)
        return

    # Handle CANCEL EDIT button press
    if text in ["❌ Скасувати редагування", "❌ Cancel Edit"]:
        await message.answer("❌ <b>Редагування скасовано. Початкові дані збережено.</b>", parse_mode=ParseMode.HTML)
        await state.set_state(PartEditingStates.in_part_info)
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

            old_mf = draft.get("three_mf")
            if old_mf:
                draft["old_three_mf"] = old_mf
            doc_id = message.document.file_id
            doc_name_clean = message.document.file_name or "model.3mf"
            draft["three_mf"] = doc_id
            draft["three_mf_name"] = doc_name_clean

            try:
                file_info = await message.bot.get_file(doc_id)
                file_bytes_io = await message.bot.download_file(file_info.file_path)
                file_bytes = file_bytes_io.read()

                import config
                from services.gcode_parser import parse_3mf_file
                save_dir = config.STORAGE_DIR / "uploads"
                save_dir.mkdir(parents=True, exist_ok=True)
                (save_dir / doc_id).write_bytes(file_bytes)

                meta = parse_3mf_file(file_bytes, doc_name)
                if meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                    draft["printer_model"] = meta["printer_model"]
                if meta.get("filament_type"):
                    draft["filament_type"] = meta["filament_type"]
            except Exception:
                pass

    await state.update_data(editing_draft=draft)

    inline_keyboard = construct_part_info_keyboard(draft, lang)
    model_info = f" (Модель: {draft.get('printer_model')})" if draft.get('printer_model') and draft.get('printer_model') != 'Unknown' else ""
    await message.answer(
        f"✏️ <b>Чернетку оновлено:</b> {html.escape(draft.get('name', 'Деталь'))}{model_info}\n"
        f"Натисніть <b>💾 Зберегти</b> для підтвердження або <b>❌ Скасувати редагування</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=inline_keyboard,
    )


# TEXT BUTTON HANDLERS FOR REPLY KEYBOARD

@router.message(F.text.in_(["🚀 Кинути на друк", "🚀 Send to Print", "Кинути на друк"]))
async def handle_print_button_text(message: Message, state: FSMContext, app: Any) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if not parts:
        await message.answer("⚠️ Склад деталей порожній!")
        return

    part_id = data.get("selected_part_id")
    if current_state == PartEditingStates.in_part_info and part_id and part_id in parts:
        part = parts[part_id]
        three_mf = part.get("three_mf")
        if not three_mf:
            await message.answer("⚠️ Для цієї деталі ще не завантажено файл .3mf!")
            return
        if not app.printers:
            await message.answer("⚠️ Немає підключених принтерів у фермі!")
            return

        u_data = await app.storage.load_user(message.from_user.id)
        lang = get_user_lang(u_data)
        kb = get_printer_select_inline_keyboard(part_id, app.printers, lang)
        await message.answer(
            f"🚀 Оберіть принтер для відправки та запуску друку деталі <b>{html.escape(part.get('name', 'Деталь'))}</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    else:
        # Prompt to select part to print
        await state.set_state(PartEditingStates.select_part_for_print)
        kb = get_parts_inline_keyboard(parts)
        await message.answer("🚀 <b>Оберіть деталь зі списку для відправки на друк:</b>", parse_mode=ParseMode.HTML, reply_markup=kb)


@router.message(F.text.in_(["✏️ Редагувати", "✏️ Edit", "✏️ Редагувати деталь", "Редагувати"]))
async def handle_edit_button_text(message: Message, state: FSMContext, app: Any) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    if not parts:
        await message.answer("⚠️ Склад деталей порожній!")
        return

    part_id = data.get("selected_part_id")
    if current_state == PartEditingStates.in_part_info and part_id and part_id in parts:
        u_data = await app.storage.load_user(message.from_user.id)
        lang = get_user_lang(u_data)
        part = parts[part_id]
        kb = construct_part_info_keyboard(part, lang)
        await message.answer("✏️ <b>Оберіть параметри деталі для змінення:</b>", parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await state.set_state(PartEditingStates.select_part_for_edit)
        kb = get_parts_inline_keyboard(parts)
        await message.answer("✏️ <b>Оберіть деталь зі списку для редагування:</b>", parse_mode=ParseMode.HTML, reply_markup=kb)


@router.message(F.text.in_(["🔍 Пошук", "🔍 Search", "🔍 Пошук деталі", "Пошук деталі", "Пошук"]))
async def handle_search_part_btn(message: Message, state: FSMContext) -> None:
    await state.set_state(PartEditingStates.search_query)
    await message.answer("🔍 <b>Введіть назву деталі для пошуку:</b>", parse_mode=ParseMode.HTML)


@router.message(PartEditingStates.search_query)
async def process_search_part_query(message: Message, state: FSMContext, app: Any) -> None:
    query = (message.text or "").strip().lower()
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    filtered = {
        pid: p for pid, p in parts.items()
        if query in (p.get("name") or "").lower() or query in (p.get("printer_model") or "").lower()
    }

    if not filtered:
        await message.answer(
            f"🔍 <b>За запитом «{html.escape(query)}» нічого не знайдено!</b>\nВведіть іншу назву або оберіть з меню:",
            parse_mode=ParseMode.HTML,
        )
        return

    kb = get_parts_inline_keyboard(filtered)
    await state.set_state(PartEditingStates.in_parts_list)
    await message.answer(
        f"🔍 <b>Знайдено деталей: {len(filtered)}</b>\nОберіть деталь зі списку:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(F.text.in_(["➕ Добавити", "➕ Add", "Добавити", "Add", "➕ Нова деталь", "➕ New Part"]))
async def start_add_part(message: Message, state: FSMContext) -> None:
    await state.set_state(PartCreatingStates.name)
    await message.answer("Введи імя:")


@router.message(PartCreatingStates.name)
async def add_part_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name:
        await message.answer("⚠️ <b>Помилка! Назва деталі не може бути порожньою.</b>\nБудь ласка, введіть назву деталі:", parse_mode=ParseMode.HTML)
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
            await message.answer("⚠️ <b>Помилка! Невірно вказано фото.</b>\nБудь ласка, надішліть файл зображення (.jpg, .png, .webp) або введіть '-' щоб пропустити:", parse_mode=ParseMode.HTML)
            return

    img_id = await extract_image_from_message(message)
    if message.text and message.text.strip() in ["-", "/skip", "пропустити"]:
        img_id = ""

    await state.update_data(image=img_id)
    await state.set_state(PartCreatingStates.count)
    await message.answer("Кількість (введіть ціле число, наприклад: 1, 5, 10):")


@router.message(PartCreatingStates.count)
async def add_part_count(message: Message, state: FSMContext) -> None:
    val = message.text.strip() if message.text else ""
    if not val.isdigit():
        await message.answer("⚠️ <b>Помилка! Кількість повинна бути цілим додатним числом (наприклад: 1, 5, 10).</b>\nСпробуйте ще раз:", parse_mode=ParseMode.HTML)
        return
    await state.update_data(count=val)
    await state.set_state(PartCreatingStates.three_mf)
    await message.answer(".3mf Файл (надішліть файл моделі або введіть '-' щоб пропустити):")


@router.message(PartCreatingStates.three_mf)
async def add_part_three_mf(message: Message, state: FSMContext, app: Any) -> None:
    if message.document:
        doc_name = str(message.document.file_name or "").lower()
        if not doc_name.endswith(".3mf"):
            await message.answer("⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть файл з розширенням .3mf або введіть '-' для пропуску:", parse_mode=ParseMode.HTML)
            return
    elif message.text and message.text.strip() not in ["-", "/skip", "пропустити"]:
        await message.answer("⚠️ <b>Помилка! Файл для друку повинен бути у форматі .3mf!</b>\nБудь ласка, надішліть .3mf документ або введіть '-' для пропуску:", parse_mode=ParseMode.HTML)
        return

    data = await state.get_data()
    doc_id = message.document.file_id if message.document else ""
    doc_name = message.document.file_name if message.document else "model.3mf"

    part_id = f"part_{int(time.time() * 1000)}"
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    try:
        cnt_val = int(data.get("count", 0))
    except ValueError:
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
        except Exception:
            pass

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
    await message.answer("Успішно!")

    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)


@router.message(F.text.in_(["🗑️ Видалити", "🗑️ Delete", "Видалити", "Delete", "🗑️ Видалити деталь"]))
async def delete_current_part(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")

    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()
    if part_id and part_id in parts:
        del parts[part_id]
        await app.storage.save_json(app.storage.parts_file, parts)
        await message.answer("Видалення деталі пройшло успішно!")

    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)


@router.message(F.text.in_(["Назад", "Back"]))
async def back_to_main_menu_or_list(message: Message, state: FSMContext, app: Any) -> None:
    current_state = await state.get_state()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    is_admin = await app.is_user_admin(message.from_user.id)

    if current_state == PartEditingStates.in_part_info:
        await open_parts_list(message, state, app, lang)
    else:
        await state.clear()
        kb = get_main_keyboard(is_admin=is_admin, lang=lang)
        await message.answer(t("warehouse_title", lang), reply_markup=kb)


@router.message(F.text.lower().in_(["🧩 звіт pdf деталей", "звіт pdf деталей", "звіт деталей pdf", "📊 звіт pdf деталей", "/pdf_parts", "pdf parts", "🧩 звіт csv деталей", "звіт csv деталей", "звіт деталей csv", "/csv_parts", "csv parts"]))
async def handle_parts_pdf_report_bot(message: Message, app: Any):
    parts = await app.storage.load_parts()

    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_parts_pdf_report
    pdf_bytes = generate_parts_pdf_report(parts)

    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"parts_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧩 <b>PDF Звіт складу готових деталей згенеровано!</b>\n\nФайл містить перелік усіх виготовлених деталей із назвою, моделлю принтера, пластиком, ціною, вагою та кількістю.",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text.lower().in_(["🧵 звіт pdf котушок", "звіт pdf котушок", "звіт котушок pdf", "/pdf_spools", "pdf spools", "/csv_spools", "csv spools"]))
async def handle_spools_pdf_report_bot(message: Message, app: Any):
    spools = await app.storage.load_spools()

    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_spools_pdf_report
    pdf_bytes = generate_spools_pdf_report(spools)

    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"spools_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧵 <b>PDF Звіт складу котушок пластику згенеровано!</b>\n\nФайл містить перелік усіх котушок на складі із залишками, ціною та статусом прив'язки до принтерів.",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text.lower().in_(["📊 звіт pdf", "📊 звіт pdf склада", "звіт pdf склада", "звіт pdf", "pdf склад", "📊 pdf report", "pdf report", "/pdf_warehouse", "pdf warehouse", "📊 звіт csv", "📊 звіт csv склада", "звіт csv склада", "звіт csv", "csv склад", "/csv_warehouse", "csv warehouse", "📊 csv report"]))
async def handle_warehouse_pdf_report_bot(message: Message, app: Any):
    spools = await app.storage.load_spools()
    parts = await app.storage.load_parts()

    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_warehouse_pdf_report
    pdf_bytes = generate_warehouse_pdf_report(spools, parts, report_type="all")

    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"warehouse_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="📊 <b>Повний PDF звіт складу згенеровано!</b>\n\nФайл містить окремі блоки для <b>Котушок пластику</b> та <b>Готових деталей</b> із назвою, ціною, вагою, кількістю та загальною сумою.",
        parse_mode=ParseMode.HTML,
    )

