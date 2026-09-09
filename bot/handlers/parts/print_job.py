"""
Send part to print job handlers.
"""

import html
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from config import logger
from bot.keyboards import get_printer_select_inline_keyboard, get_parts_inline_keyboard
from bot.states import PartEditingStates
from utils.i18n import get_user_lang

router = Router()


@router.message(
    PartEditingStates.in_parts_list,
    F.text.lower().in_(["друк", "🚀 друк", "print", "🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
@router.message(
    PartEditingStates.in_part_info,
    F.text.lower().in_(["друк", "🚀 друк", "print", "🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
@router.message(
    F.text.lower().in_(["🚀 кинути на друк", "кинути на друк", "🚀 send to print", "send to print"])
)
async def handle_print_part_start(message: Message, state: FSMContext, app: Any) -> None:
    data = await state.get_data()
    part_id = data.get("selected_part_id")
    parts = await app.storage.load_parts()
    if not parts:
        await message.answer("⚠️ На Складі немає деталей для друку.")
        return

    current_state = await state.get_state()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)

    if current_state == PartEditingStates.in_part_info and part_id and part_id in parts:
        part = parts[part_id]
        spools_map = await app.storage.load_spools() if hasattr(app, "storage") else None
        ikb = get_printer_select_inline_keyboard(part_id, app.printers, part=part, lang=lang, spools_map=spools_map)
        await message.answer(f"🖨️ <b>Оберіть принтер для друку деталі «{html.escape(part.get('name', 'Деталь'))}»:</b>", parse_mode=ParseMode.HTML, reply_markup=ikb)
    else:
        await state.set_state(PartEditingStates.select_part_for_print)
        await message.answer("Оберіть деталь для відправки на друк:", reply_markup=get_parts_inline_keyboard(parts))


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
    spools_map = await app.storage.load_spools() if hasattr(app, "storage") else None
    kb = get_printer_select_inline_keyboard(part_id, app.printers, part=part, lang=lang, spools_map=spools_map)
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
    app_ref = getattr(callback.bot, "_app_ref", None) or app
    spools_map = await app_ref.storage.load_spools() if hasattr(app_ref, "storage") else None
    active_fil = get_printer_active_filament(printer, spools_map)
    comp = check_compatibility(part.get("printer_model", ""), part.get("filament_type", ""), printer.name, active_fil)
    if not comp.get("compatible"):
        reason = comp.get("reason", "🛑 Несумісний принтер або пластик!")
        await callback.answer(f"🛑 ДРУК БЛОКОВАНО: {reason}", show_alert=True)
        if comp.get("reason_type") == "PRINTER":
            p_model = part.get("printer_model") or comp.get("sliced_model", "Невідомо")
            await callback.message.answer(
                f"🚨 <b>ПОМИЛКА СУМІСНОСТІ! ДРУК БЛОКОВАНО!</b>\n\n"
                f"🛑 <b>Принтер несумісний з файлом!</b>\n"
                f"• <b>Модель у файлі:</b> <code>{html.escape(str(p_model))}</code>\n"
                f"• <b>Обраний принтер:</b> <code>{html.escape(printer.name)}</code>\n\n"
                f"<i>Будь ласка, оберіть сумісний принтер зі списку або наріжте деталь для {html.escape(printer.name)}.</i>",
                parse_mode=ParseMode.HTML,
            )
        else:
            req_fil = part.get("filament_type") or comp.get("sliced_filament", "Невідомо")
            curr_fil = active_fil or comp.get("target_filament", "Невідомо")
            await callback.message.answer(
                f"🚨 <b>ПОМИЛКА СУМІСНОСТІ! ДРУК БЛОКОВАНО!</b>\n\n"
                f"🛑 <b>Філамент несумісний з файлом!</b>\n"
                f"• <b>Необхідний пластик:</b> <code>{html.escape(str(req_fil))}</code>\n"
                f"• <b>Пластик на принтері:</b> <code>{html.escape(str(curr_fil))}</code>\n\n"
                f"<i>Будь ласка, заправте потрібний пластик на принтер або оберіть інший принтер.</i>",
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


