"""
Parts warehouse view handlers.
"""

import html
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
    get_parts_inline_keyboard,
    get_parts_reply_keyboard,
    get_search_reply_keyboard,
)
from bot.states import PartEditingStates
from utils.i18n import get_user_lang

router = Router()


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


def resolve_part_metadata(part: dict[str, Any]) -> bool:
    """
    Auto-fills missing printer_model, filament_type, weight_g, time_mins from 3MF file on disk.
    Returns True if part was modified.
    """
    modified = False
    try:
        weight = float(part.get("weight_g", 0.0) or part.get("weight", 0.0) or 0.0)
    except (ValueError, TypeError):
        weight = 0.0

    try:
        time_mins = int(part.get("time_mins", 0) or part.get("print_time", 0) or 0)
    except (ValueError, TypeError):
        time_mins = 0

    model = part.get("printer_model")
    fil = part.get("filament_type")

    three_mf = part.get("three_mf")
    three_mf_name = part.get("three_mf_name")

    if (weight <= 0.0 or time_mins <= 0 or not model or model == "Unknown" or not fil) and (three_mf or three_mf_name):
        import config
        from services.gcode_parser import parse_3mf_file
        for fname in [three_mf, three_mf_name]:
            if not fname:
                continue
            for d in [config.STORAGE_DIR / "uploads", config.STORAGE_DIR / "parts_files"]:
                p_path = d / fname
                if p_path.exists() and p_path.is_file():
                    try:
                        meta = parse_3mf_file(p_path.read_bytes(), three_mf_name or p_path.name)
                        if weight <= 0.0 and meta.get("weight_g"):
                            w = float(meta["weight_g"])
                            part["weight_g"] = w
                            part["weight"] = w
                            weight = w
                            modified = True
                        if time_mins <= 0 and meta.get("time_mins"):
                            t_m = int(meta["time_mins"])
                            part["time_mins"] = t_m
                            part["print_time"] = t_m
                            time_mins = t_m
                            modified = True
                        if (not model or model == "Unknown") and meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                            part["printer_model"] = meta["printer_model"]
                            model = meta["printer_model"]
                            modified = True
                        if not fil and meta.get("filament_type"):
                            part["filament_type"] = meta["filament_type"]
                            fil = meta["filament_type"]
                            modified = True
                        if not part.get("nozzle_diameter") and meta.get("nozzle_diameter"):
                            part["nozzle_diameter"] = str(meta["nozzle_diameter"])
                            modified = True
                        break
                    except Exception:
                        pass
            if weight > 0.0:
                break

    return modified


async def send_part_info(target_message: Message, part: dict[str, Any], text_keyboard: ReplyKeyboardMarkup, inline_keyboard: InlineKeyboardMarkup) -> None:
    await target_message.answer(".", reply_markup=text_keyboard)

    resolve_part_metadata(part)

    img = str(part.get("image", "") or "").strip()
    name = html.escape(part.get("name", "Деталь"))
    p_model = part.get("printer_model")
    model_para = f"\n🖨️ <b>Принтер:</b> {html.escape(p_model)}" if p_model and p_model != "Unknown" else ""
    p_nozzle = part.get("nozzle_diameter")
    nozzle_para = f"\n🎯 <b>Сопло:</b> <code>{html.escape(str(p_nozzle))} мм</code>" if p_nozzle else ""
    p_fil = part.get("filament_type")
    fil_para = f"\n🧵 <b>Пластик:</b> {html.escape(p_fil)}" if p_fil else ""

    cnt = part.get("count", part.get("quantity", 0))

    try:
        weight = float(part.get("weight_g", 0.0) or part.get("weight", 0.0) or 0.0)
    except (ValueError, TypeError):
        weight = 0.0

    try:
        time_mins = int(part.get("time_mins", 0) or part.get("print_time", 0) or 0)
    except (ValueError, TypeError):
        time_mins = 0

    weight_para = ""
    if weight > 0:
        if cnt > 1:
            weight_para = f"\n⚖️ <b>Вага 1 шт:</b> {weight:.1f} г (загалом: {weight * cnt:.1f} г)"
        else:
            weight_para = f"\n⚖️ <b>Вага:</b> {weight:.1f} г"

    time_para = ""
    if time_mins > 0:
        from services.gcode_parser import format_print_time_human
        time_para = f"\n⏱️ <b>Час друку:</b> {format_print_time_human(time_mins)}"

    caption_text = f"🧩 <b>{name}</b>{model_para}{nozzle_para}{fil_para}\n📦 <b>Кількість:</b> {cnt} шт{weight_para}{time_para}"

    photo_sent = False
    if img:
        try:
            if img.startswith("http://") or img.startswith("https://") or (len(img) > 15 and "/" not in img and "\\" not in img):
                await target_message.answer_photo(photo=img, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                photo_sent = True
            else:
                import config
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

    current_state = await state.get_state()
    part = parts[part_id]
    u_data = await app.storage.load_user(callback.from_user.id)
    lang = get_user_lang(u_data)

    if current_state == PartEditingStates.select_part_for_edit:
        await state.set_state(PartEditingStates.in_part_info)
        await state.update_data(selected_part_id=part_id)
        ikb = construct_part_info_keyboard(part, lang)
        await callback.message.answer(
            f"✏️ <b>Редагування деталі «{html.escape(part.get('name', 'Деталь'))}»:</b>\nОберіть поле для зміни:",
            parse_mode=ParseMode.HTML,
            reply_markup=ikb,
        )
        await callback.answer()
        return

    if current_state == PartEditingStates.select_part_for_delete:
        del parts[part_id]
        await app.storage.save_json(app.storage.parts_file, parts)
        await callback.message.answer("✅ <b>Деталь успішно видалено!</b>", parse_mode=ParseMode.HTML)
        await open_parts_list(callback.message, state, app, lang)
        await callback.answer()
        return

    if current_state == PartEditingStates.select_part_for_print:
        three_mf = part.get("three_mf")
        if not three_mf:
            await callback.answer("⚠️ Для цієї деталі ще не завантажено файл .3mf!", show_alert=True)
            return
        if not app.printers:
            await callback.answer("⚠️ Немає підключених принтерів у фермі!", show_alert=True)
            return
        from bot.keyboards import get_printer_select_inline_keyboard
        spools_map = await app.storage.load_spools() if hasattr(app, "storage") else None
        kb = get_printer_select_inline_keyboard(part_id, app.printers, part=part, lang=lang, spools_map=spools_map)
        model_str = f"\n🖨️ <b>Модель у файлі:</b> {html.escape(part.get('printer_model'))}" if part.get('printer_model') and part.get('printer_model') != 'Unknown' else ""
        await callback.message.answer(
            f"🚀 Оберіть принтер для відправки та запуску друку деталі <b>{html.escape(part.get('name', 'Деталь'))}</b>{model_str}:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        await callback.answer()
        return

    await state.set_state(PartEditingStates.in_part_info)
    await state.update_data(selected_part_id=part_id)

    text_keyboard = get_part_action_reply_keyboard(lang)
    inline_keyboard = construct_part_info_keyboard(part, lang)

    await send_part_info(callback.message, part, text_keyboard, inline_keyboard)

    three_mf = part.get("three_mf")
    if three_mf:
        try:
            is_file_id = bool(
                three_mf
                and not three_mf.startswith(("/", "\\", "http://", "https://"))
                and "." not in three_mf
                and "/" not in three_mf
                and "\\" not in three_mf
                and len(three_mf) >= 20
            )
            if is_file_id:
                await callback.message.answer(".3mf:")
                await callback.message.answer_document(three_mf)
            else:
                import config
                clean_name = three_mf.replace("\\", "/").split("/")[-1]
                clean_rel = three_mf.lstrip("/").lstrip("\\")
                possible_paths = [
                    config.STORAGE_DIR / "uploads" / clean_name,
                    config.STORAGE_DIR / "parts_files" / clean_name,
                    config.STORAGE_DIR / clean_name,
                    config.STORAGE_DIR / clean_rel,
                    Path(three_mf),
                ]
                found_path = None
                for p in possible_paths:
                    if p.exists() and p.is_file():
                        found_path = p
                        break
                if found_path:
                    doc_fname = part.get("three_mf_name") or clean_name
                    await callback.message.answer(".3mf:")
                    await callback.message.answer_document(FSInputFile(found_path, filename=doc_fname))
        except Exception as e:
            logger.warning(f"Error sending .3mf document: {e}")

    await callback.answer()


SEARCH_FINISH_TEXTS = [
    "❌ закінчити пошук", "закінчити пошук", "❌ finish search", "finish search",
    "❌ завершити пошук", "завершити пошук",
    "закінчити", "стоп", "stop", "вихід", "exit",
    "❌ скасувати", "скасувати", "cancel", "❌ cancel", "/cancel",
    "відміна", "відмінити",
    "⬅️ до списку деталей", "до списку деталей", "⬅️ back to parts", "back to parts",
    "⬅️ назад до списку", "назад до списку", "⬅️ назад", "назад", "⬅️ back", "back",
]

SEARCH_MAIN_MENU_TEXTS = [
    "головне меню", "main menu", "меню", "menu", "/menu",
    "🏠 головне меню", "🏠 main menu", "🏠 меню",
    "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню",
]

SEARCH_NAVIGATION_TEXTS = [
    "📦 склад", "склад", "📦 warehouse", "warehouse", "📦 склад котушок", "склад котушок",
    "🧵 філамент & ams", "філамент & ams", "🧵 філамент", "філамент", "🧵 filament", "filament",
    "🖨️ принтери", "принтери", "🖨️ printers", "printers",
    "📊 стан ферми", "стан ферми", "📊 farm status", "farm status", "ферма",
    "🧩 склад деталей", "склад деталей", "🧩 parts stock", "parts stock",
    "➕ додати котушку", "додати котушку", "➕ add spool", "add spool",
    "➕ добавити", "добавити", "➕ додати", "додати", "➕ add", "add", "➕ нова деталь", "нова деталь", "додати деталь", "добавити деталь",
    "/start", "/printers", "/warehouse", "/farm",
]

SEARCH_PDF_TEXTS = [
    "📊 звіт деталей (pdf)", "звіт деталей (pdf)", "📊 parts report (pdf)", "parts report (pdf)",
    "🧩 звіт pdf деталей", "звіт pdf деталей", "звіт деталей pdf", "📊 звіт pdf деталей",
    "звіт деталей", "звіт по деталях", "/pdf_parts", "pdf parts",
]


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["🔍 пошук", "пошук", "🔍 search", "search", "🔍 пошук деталі", "пошук деталі", "🔍 search part", "search part"]),
)
@router.message(
    F.text.lower().in_(["🔍 пошук", "пошук", "🔍 search", "search", "🔍 пошук деталі", "пошук деталі", "🔍 search part", "search part"]),
)
async def handle_search_part_btn(message: Message, state: FSMContext, app: Any = None) -> None:
    await state.set_state(PartEditingStates.search_query)
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)
    reply_kb = get_search_reply_keyboard(lang)
    await message.answer(
        "🔍 <b>Введіть назву деталі для пошуку:</b>\nНатисніть <b>❌ Закінчити пошук</b> або <b>Головне меню</b> для виходу."
        if lang != "en"
        else "🔍 <b>Enter part name to search:</b>\nClick <b>❌ Finish Search</b> or <b>Main Menu</b> to exit.",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_kb,
    )


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(
        [
            "назад", "back", "⬅️ назад", "⬅️ back", "⬅️ до списку деталей",
            "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку", "назад до списку",
            "головне меню", "main menu", "🏠 головне меню", "🏠 main menu", "меню", "menu",
            "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню",
            "❌ закінчити пошук", "закінчити пошук", "❌ finish search", "finish search",
        ]
    ),
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(
        [
            "назад", "back", "⬅️ назад", "⬅️ back", "⬅️ до списку деталей",
            "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку", "назад до списку",
            "головне меню", "main menu", "🏠 головне меню", "🏠 main menu", "меню", "menu",
            "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню",
            "❌ закінчити пошук", "закінчити пошук", "❌ finish search", "finish search",
        ]
    ),
)
@router.message(
    PartEditingStates.search_query,
    F.text.lower().in_(
        [
            "назад", "back", "⬅️ назад", "⬅️ back", "⬅️ до списку деталей",
            "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку", "назад до списку",
            "головне меню", "main menu", "🏠 головне меню", "🏠 main menu", "меню", "menu",
            "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню",
            "❌ закінчити пошук", "закінчити пошук", "❌ finish search", "finish search",
        ]
    ),
)
@router.message(
    F.text.lower().in_(
        [
            "⬅️ до списку деталей", "до списку деталей", "⬅️ back to parts", "back to parts", "⬅️ назад до списку деталей",
            "❌ закінчити пошук", "закінчити пошук", "❌ finish search", "finish search",
        ]
    )
)
async def back_to_main_menu_or_list(message: Message, state: FSMContext, app: Any) -> None:
    current_state = await state.get_state()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    is_admin = await app.is_user_admin(message.from_user.id)

    text_low = (message.text or "").strip().lower()
    if text_low in [
        "головне меню", "main menu", "🏠 головне меню", "🏠 main menu", "меню", "menu",
        "⬅️ головне меню", "⬅️ main menu", "повернутись в меню", "назад в меню", "⬅️ назад в меню"
    ]:
        await state.clear()
        kb = get_main_keyboard(is_admin=is_admin, lang=lang)
        from utils.i18n import t
        await message.answer(t("warehouse_title", lang), reply_markup=kb)
        return

    if current_state in (
        PartEditingStates.in_part_info,
        PartEditingStates.property_edit,
        PartEditingStates.select_part_for_print,
        PartEditingStates.select_part_for_edit,
        PartEditingStates.select_part_for_delete,
        PartEditingStates.search_query,
    ):
        await open_parts_list(message, state, app, lang)
    else:
        await state.clear()
        kb = get_main_keyboard(is_admin=is_admin, lang=lang)
        from utils.i18n import t
        await message.answer(t("warehouse_title", lang), reply_markup=kb)


@router.message(PartEditingStates.search_query)
@router.message(PartEditingStates.in_parts_list)
async def process_search_part_query(message: Message, state: FSMContext, app: Any) -> None:
    raw_text = (message.text or "").strip()
    text_lower = raw_text.lower()
    u_data = await app.storage.load_user(message.from_user.id) if (app and message.from_user) else None
    lang = get_user_lang(u_data)

    if text_lower in SEARCH_FINISH_TEXTS:
        await open_parts_list(message, state, app, lang)
        return

    if text_lower in SEARCH_MAIN_MENU_TEXTS:
        await state.clear()
        is_admin = await app.is_user_admin(str(message.from_user.id)) if (app and message.from_user) else False
        from utils.i18n import t
        await message.answer(t("warehouse_title", lang), reply_markup=get_main_keyboard(is_admin, lang))
        return

    if text_lower in SEARCH_PDF_TEXTS:
        await state.clear()
        await handle_parts_pdf_report_bot(message, app)
        return

    if text_lower in ["🔍 пошук", "пошук", "🔍 search", "search", "🔍 пошук деталі", "пошук деталі", "🔍 search part", "search part"]:
        reply_kb = get_search_reply_keyboard(lang)
        await message.answer(
            "🔍 <b>Введіть назву деталі для пошуку:</b>\nНатисніть <b>❌ Закінчити пошук</b> для повернення до списку деталей:"
            if lang != "en"
            else "🔍 <b>Enter part name to search:</b>\nClick <b>❌ Finish Search</b> to return to parts list:",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_kb,
        )
        return

    if text_lower in SEARCH_NAVIGATION_TEXTS:
        await state.clear()
        if text_lower in ["➕ додати котушку", "додати котушку", "➕ add spool", "add spool"]:
            from bot.handlers.filament.add import handle_add_spool_start
            await handle_add_spool_start(message, app, state)
        elif text_lower in [
            "📦 склад", "склад", "📦 warehouse", "warehouse", "📦 склад котушок", "склад котушок",
            "🧵 філамент & ams", "філамент & ams", "🧵 філамент", "філамент", "🧵 filament", "filament"
        ]:
            from bot.handlers.filament.view import handle_filament_menu
            await handle_filament_menu(message, app, state)
        elif text_lower in ["🖨️ принтери", "принтери", "🖨️ printers", "printers"]:
            from bot.handlers.printers.view import handle_list_printers
            await handle_list_printers(message, app, state)
        elif text_lower in ["📊 стан ферми", "стан ферми", "📊 farm status", "farm status", "ферма"]:
            from bot.handlers.dashboard import handle_dashboard
            await handle_dashboard(message, app, state)
        elif text_lower in ["🧩 склад деталей", "склад деталей", "🧩 parts stock", "parts stock"]:
            await open_parts_list(message, state, app, lang)
        elif text_lower in ["➕ добавити", "добавити", "➕ додати", "додати", "➕ add", "add", "➕ нова деталь", "нова деталь", "додати деталь", "добавити деталь"]:
            from bot.handlers.parts.add import handle_add_part_start
            await handle_add_part_start(message, app, state)
        elif text_lower in ["/start"]:
            from bot.handlers.start import cmd_start
            await cmd_start(message, app, state)
        else:
            is_admin = await app.is_user_admin(str(message.from_user.id)) if (app and message.from_user) else False
            from utils.i18n import t
            await message.answer(t("warehouse_title", lang), reply_markup=get_main_keyboard(is_admin, lang))
        return

    query = text_lower
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    filtered = {
        pid: p
        for pid, p in parts.items()
        if query in (p.get("name") or "").lower() or query in (p.get("printer_model") or "").lower()
    }

    if not filtered:
        await state.set_state(PartEditingStates.search_query)
        await message.answer(
            f"🔍 <b>За запитом «{html.escape(raw_text)}» нічого не знайдено!</b>\nСпробуйте іншу назву або натисніть <b>❌ Закінчити пошук</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=get_search_reply_keyboard(lang),
        )
        return

    kb = get_parts_inline_keyboard(filtered)
    await state.set_state(PartEditingStates.in_parts_list)
    reply_kb = get_parts_reply_keyboard(lang)
    await message.answer(".", reply_markup=reply_kb)
    await message.answer(
        f"🔍 <b>Знайдено деталей: {len(filtered)}</b>\nОберіть деталь зі списку:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(
    F.text.lower().in_(
        [
            "📊 звіт деталей (pdf)", "звіт деталей (pdf)", "📊 parts report (pdf)", "parts report (pdf)",
            "🧩 звіт pdf деталей", "звіт pdf деталей", "звіт деталей pdf", "📊 звіт pdf деталей",
            "звіт деталей", "звіт по деталях", "/pdf_parts", "pdf parts",
        ]
    )
)
async def handle_parts_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_parts_pdf_report

    parts = await app.storage.load_parts()
    dirty = False
    if isinstance(parts, dict):
        for p in parts.values():
            if isinstance(p, dict) and resolve_part_metadata(p):
                dirty = True
        if dirty:
            await app.storage.save_parts(parts)

    pdf_bytes = generate_parts_pdf_report(parts)
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"parts_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧩 <b>PDF Звіт складу готових деталей згенеровано!</b>\n\nФайл містить виключно перелік усіх готових 3D деталей із назвою, моделлю принтера, пластиком, ціною, вагою та кількістю.",
        parse_mode=ParseMode.HTML,
    )


@router.message(
    F.text.lower().in_(
        [
            "🧵 звіт котушок (pdf)", "звіт котушок (pdf)", "🧵 звіт pdf котушок", "звіт pdf котушок",
            "звіт котушок pdf", "звіт котушок", "/pdf_spools", "pdf spools",
        ]
    )
)
async def handle_spools_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_spools_pdf_report

    spools = await app.storage.load_spools()
    pdf_bytes = generate_spools_pdf_report(spools, printers=getattr(app, "printers", None))
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"spools_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="🧵 <b>PDF Звіт складу котушок пластику згенеровано!</b>\n\nФайл містить перелік усіх котушок на складі із залишками, ціною та статусом прив'язки до принтерів.",
        parse_mode=ParseMode.HTML,
    )


@router.message(
    F.text.lower().in_(
        [
            "🏢 загальний звіт складу (pdf)", "загальний звіт складу (pdf)", "🏢 загальний звіт (pdf)",
            "загальний звіт (pdf)", "📊 звіт pdf склада", "звіт pdf склада", "звіт всього складу",
            "звіт всього складу (pdf)", "pdf склад", "📊 pdf warehouse", "pdf warehouse", "/pdf_warehouse",
        ]
    )
)
async def handle_warehouse_pdf_report_bot(message: Message, app: Any):
    import time
    from aiogram.types import BufferedInputFile
    from services.report_generator import generate_warehouse_pdf_report

    spools = await app.storage.load_spools()
    parts = await app.storage.load_parts()
    pdf_bytes = generate_warehouse_pdf_report(spools, parts, report_type="all", printers=getattr(app, "printers", None))
    date_str = time.strftime("%Y-%m-%d_%H-%M")
    doc_file = BufferedInputFile(pdf_bytes, filename=f"warehouse_report_{date_str}.pdf")

    await message.answer_document(
        doc_file,
        caption="📊 <b>Повний PDF звіт складу згенеровано!</b>\n\nФайл містить окремі блоки для <b>Котушок пластику</b> та <b>Готових деталей</b>.",
        parse_mode=ParseMode.HTML,
    )

