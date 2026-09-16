"""
Farm dashboard and printing history handlers.
"""

from __future__ import annotations

import html
import time
from typing import Any

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

router = Router()


@router.message(F.text.lower().in_(["📊 стан ферми", "стан ферми", "ферма", "📊 farm status", "farm status"]))
async def handle_dashboard(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    if not app.printers:
        await message.answer(
            "⚠️ No printers added yet!" if is_en else "⚠️ У базі немає доданих принтерів."
        )
        return

    if is_en:
        dash_txt = "<b>🏭 3D Farm Dashboard</b>\n\n"
        dash_txt += f"<b>Total Printers: {len(app.printers)}</b>\n\n"
    else:
        dash_txt = "<b>🏭 Дашборд 3D Ферми</b>\n\n"
        dash_txt += f"<b>Всього принтерів: {len(app.printers)}</b>\n\n"

    for pid, p in app.printers.items():
        p_name = html.escape(p.name)
        is_p_online = getattr(p, "is_online", True)
        mapped_st = getattr(p, "mapped_state", "ONLINE")

        if not is_p_online or mapped_st == "OFFLINE":
            st_emoji = "🔴"
            st_str = "Офлайн" if not is_en else "OFFLINE"
        elif mapped_st == "RUNNING":
            st_emoji = "🟢"
            st_str = "Друкує" if not is_en else "PRINTING"
        elif mapped_st == "PAUSE":
            st_emoji = "⏸️"
            st_str = "Пауза" if not is_en else "PAUSE"
        else:
            st_emoji = "⚪"
            st_str = "Онлайн" if not is_en else "ONLINE"

        spd_str = (
            f" ({p.spd_mag}%)"
            if getattr(p, "spd_mag", 100) and getattr(p, "spd_mag", 100) != 100 and is_p_online
            else ""
        )

        dash_txt += f"{st_emoji} <b>{p_name}</b>: <code>{st_str}</code>{spd_str}\n"

        if not is_p_online or mapped_st == "OFFLINE":
            dash_txt += f"   🔌 <i>{'Вимкнений або немає зв\'язку' if not is_en else 'Offline / Powered off'}</i>\n"
        elif mapped_st in ["RUNNING", "PAUSE"]:
            from bot.handlers.printers.view import format_remaining_time
            sub_task = html.escape(p.subtask_name or ("Model" if is_en else "Модель"))
            min_lbl = "min" if is_en else "хв"
            rem_m = getattr(p, "mc_remaining_time", 0)
            rem_str = format_remaining_time(rem_m, is_en)
            time_display = f"~{rem_str} ({rem_m} {min_lbl})" if rem_str else f"~{rem_m} {min_lbl}"
            dash_txt += f"   📄 <i>{sub_task}</i> ({p.mc_percent}%) | ⏱️ {time_display}\n"
            dash_txt += f"   🔥 {p.nozzle_temper}°C | 🛏️ {p.bed_temper}°C | 🧵 {p.filament_grams}g\n"
        else:
            rem_lbl = "Remaining:" if is_en else "Залишок:"
            dash_txt += f"   📦 {rem_lbl} {p.filament_grams}g | 🧵 {html.escape(p.filament_type)}\n"
        dash_txt += "\n"

    await message.answer(dash_txt, parse_mode=ParseMode.HTML)


from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup

from bot.keyboards import (
    get_history_date_filter_keyboard,
    get_history_inline_keyboard,
    get_history_printer_filter_keyboard,
)


def filter_history_records(
    history: list[dict[str, Any]],
    app,
    printer_filter: str = "all",
    date_filter: str = "all",
) -> list[dict[str, Any]]:
    filtered = list(history)

    # 1. Filter by printer
    if printer_filter and printer_filter != "all":
        target_p = app.printers.get(printer_filter) if hasattr(app, "printers") else None
        target_name = target_p.name if target_p else printer_filter
        filtered = [
            item
            for item in filtered
            if str(item.get("printer_id", "")) == str(printer_filter)
            or item.get("printer_name") == target_name
            or item.get("printer") == target_name
            or item.get("printer_name") == printer_filter
        ]

    # 2. Filter by date/period
    now = time.time()
    if date_filter == "today":
        import datetime
        today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        filtered = [item for item in filtered if float(item.get("timestamp", 0)) >= today_start]
    elif date_filter == "7d":
        seven_days_ago = now - 7 * 86400
        filtered = [item for item in filtered if float(item.get("timestamp", 0)) >= seven_days_ago]
    elif date_filter == "30d":
        thirty_days_ago = now - 30 * 86400
        filtered = [item for item in filtered if float(item.get("timestamp", 0)) >= thirty_days_ago]

    # Sort descending by timestamp
    filtered.sort(key=lambda x: float(x.get("timestamp", 0)), reverse=True)
    return filtered


def get_filter_labels(app, printer_filter: str, date_filter: str, is_en: bool = False):
    if printer_filter == "all":
        p_label = "All printers" if is_en else "Усі принтери"
    else:
        target_p = app.printers.get(printer_filter) if hasattr(app, "printers") else None
        p_label = target_p.name if target_p else printer_filter

    if date_filter == "today":
        d_label = "Today" if is_en else "Сьогодні"
    elif date_filter == "7d":
        d_label = "7 days" if is_en else "7 днів"
    elif date_filter == "30d":
        d_label = "30 days" if is_en else "30 днів"
    else:
        d_label = "All time" if is_en else "Увесь час"

    return p_label, d_label


def render_history_text(
    filtered: list[dict[str, Any]],
    p_label: str,
    d_label: str,
    page: int,
    total_pages: int,
    is_en: bool = False,
) -> str:
    total_prints = len(filtered)
    total_g = round(sum(float(item.get("weight_g", 0.0)) for item in filtered), 1)

    if is_en:
        hist_txt = (
            f"<b>📜 Farm Print History & Statistics</b>\n\n"
            f"🔍 <b>Filter:</b> 🖨️ {html.escape(p_label)} | 📅 {d_label}\n"
            f"📊 Total completed: <b>{total_prints} items</b>\n"
            f"🧵 Total filament used: <b>{total_g}g</b>\n"
            f"-----------------------------------\n"
        )
    else:
        hist_txt = (
            f"<b>📜 Журнал & Статистика Ферми</b>\n\n"
            f"🔍 <b>Фільтр:</b> 🖨️ {html.escape(p_label)} | 📅 {d_label}\n"
            f"📊 Загалом надруковано: <b>{total_prints} деталей</b>\n"
            f"🧵 Витрачено пластику: <b>{total_g}g</b>\n"
            f"-----------------------------------\n"
        )

    if not filtered:
        hist_txt += (
            "<i>No print jobs match the selected filters.</i>\n"
            if is_en
            else "<i>За обраними фільтрами записів не знайдено.</i>\n"
        )
        return hist_txt

    ITEMS_PER_PAGE = 5
    start_idx = (page - 1) * ITEMS_PER_PAGE
    page_items = filtered[start_idx : start_idx + ITEMS_PER_PAGE]

    for idx, item in enumerate(page_items, start=start_idx + 1):
        ts = item.get("timestamp", time.time())
        dt_str = time.strftime("%d.%m %H:%M", time.localtime(ts))
        p_name = html.escape(item.get("printer_name", "Printer" if is_en else "Принтер"))
        sub = html.escape(item.get("subtask_name", "Model" if is_en else "Модель"))
        w = item.get("weight_g", 0.0)
        f_type = html.escape(item.get("filament_type", ""))
        type_str = f" • {f_type}" if f_type else ""
        hist_txt += f"<b>{idx}. {p_name}</b> ({dt_str})\n   📄 <i>{sub}</i>\n   ⚖️ {w}g{type_str}\n\n"

    page_lbl = f"Page {page} of {total_pages}" if is_en else f"Сторінка {page} з {total_pages}"
    hist_txt += f"-----------------------------------\n📄 <b>{page_lbl}</b>"
    return hist_txt


async def export_history_pdf_impl(app, chat_id: str, message_to_reply, user_lang: str):
    is_en = user_lang == "en"
    history = await app.storage.load_history()
    if not history:
        await message_to_reply.answer(
            "⚠️ Print log is empty, nothing to export." if is_en else "⚠️ Журнал друку порожній, немає даних для експорту."
        )
        return

    user = await app.storage.load_user(chat_id)
    ctx = user.get("context_data", {}).get("history_filter", {})
    p_filter = ctx.get("printer", "all")
    d_filter = ctx.get("period", "all")

    filtered = filter_history_records(history, app, p_filter, d_filter)
    if not filtered:
        await message_to_reply.answer(
            "⚠️ No records found for selected filters." if is_en else "⚠️ За обраними фільтрами записів для експорту не знайдено."
        )
        return

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    from services.report_generator import generate_history_pdf_report

    pdf_bytes = generate_history_pdf_report(filtered)
    date_str = time.strftime("%Y%m%d_%H%M")
    filter_suffix = f"_{p_filter}" if p_filter != "all" else ""
    doc_file = BufferedInputFile(pdf_bytes, filename=f"farm_history{filter_suffix}_{date_str}.pdf")

    caption_filter = f"\n🔍 Фільтр: 🖨️ {p_label} | 📅 {d_label}" if (p_filter != "all" or d_filter != "all") else ""
    caption = (
        f"📊 *3D Farm Print History PDF Report*{caption_filter}"
        if is_en
        else f"📊 *PDF звіт історії друку 3D Ферми*{caption_filter}"
    )
    await message_to_reply.answer_document(
        document=doc_file,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(
    F.text.lower().in_(
        [
            "📜 історія друку",
            "історія друку",
            "історія",
            "журнал друку",
            "📜 print history",
            "print history",
            "history",
            "/history",
            "/history_log",
            "/prints",
        ]
    )
)
async def handle_history(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    history = await app.storage.load_history()
    if not history:
        await message.answer(
            "📜 <b>Print history log is empty!</b>" if is_en else "📜 <b>Журнал друку порожній!</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    ctx = user.setdefault("context_data", {}).setdefault("history_filter", {"printer": "all", "period": "all", "page": 1})
    p_filter = ctx.get("printer", "all")
    d_filter = ctx.get("period", "all")
    page = int(ctx.get("page", 1))

    filtered = filter_history_records(history, app, p_filter, d_filter)
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    ctx["page"] = page
    await app.storage.save_user(user)

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, page, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, p_filter, d_filter, page, total_pages, lang=u_lang)

    pdf_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Download PDF Report" if is_en else "📥 Завантажити PDF звіт")],
            [KeyboardButton(text="⬅️ Back" if is_en else "⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
    # Set reply keyboard for persistent navigation buttons while displaying inline interactive controls
    await message.answer(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)


@router.callback_query(F.data == "hist_menu_p")
async def handle_hist_menu_printer(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.get("context_data", {}).get("history_filter", {})
    p_filter = ctx.get("printer", "all")

    ikb = get_history_printer_filter_keyboard(app, current_filter=p_filter, lang=u_lang)
    title = "🖨️ <b>Оберіть принтер для фільтрації історії:</b>" if not is_en else "🖨️ <b>Select printer to filter history:</b>"
    try:
        await callback.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("hist_p:"))
async def handle_hist_select_printer(callback: CallbackQuery, app):
    p_filter = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.setdefault("context_data", {}).setdefault("history_filter", {})
    ctx["printer"] = p_filter
    ctx["page"] = 1
    await app.storage.save_user(user)

    history = await app.storage.load_history()
    d_filter = ctx.get("period", "all")
    filtered = filter_history_records(history, app, p_filter, d_filter)
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, 1, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, p_filter, d_filter, 1, total_pages, lang=u_lang)

    try:
        await callback.message.edit_text(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data == "hist_menu_d")
async def handle_hist_menu_date(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.get("context_data", {}).get("history_filter", {})
    d_filter = ctx.get("period", "all")

    ikb = get_history_date_filter_keyboard(current_filter=d_filter, lang=u_lang)
    title = "📅 <b>Оберіть період для фільтрації історії:</b>" if not is_en else "📅 <b>Select period to filter history:</b>"
    try:
        await callback.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("hist_d:"))
async def handle_hist_select_date(callback: CallbackQuery, app):
    d_filter = callback.data.split(":", 1)[1]
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.setdefault("context_data", {}).setdefault("history_filter", {})
    ctx["period"] = d_filter
    ctx["page"] = 1
    await app.storage.save_user(user)

    history = await app.storage.load_history()
    p_filter = ctx.get("printer", "all")
    filtered = filter_history_records(history, app, p_filter, d_filter)
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, 1, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, p_filter, d_filter, 1, total_pages, lang=u_lang)

    try:
        await callback.message.edit_text(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("hist_page:"))
async def handle_hist_page(callback: CallbackQuery, app):
    try:
        page = int(callback.data.split(":", 1)[1])
    except (ValueError, TypeError):
        page = 1

    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.setdefault("context_data", {}).setdefault("history_filter", {})
    ctx["page"] = page
    await app.storage.save_user(user)

    history = await app.storage.load_history()
    p_filter = ctx.get("printer", "all")
    d_filter = ctx.get("period", "all")
    filtered = filter_history_records(history, app, p_filter, d_filter)
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, page, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, p_filter, d_filter, page, total_pages, lang=u_lang)

    try:
        await callback.message.edit_text(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data == "hist_reset")
async def handle_hist_reset(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    user.setdefault("context_data", {})["history_filter"] = {"printer": "all", "period": "all", "page": 1}
    await app.storage.save_user(user)

    history = await app.storage.load_history()
    filtered = filter_history_records(history, app, "all", "all")
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)

    p_label, d_label = get_filter_labels(app, "all", "all", is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, 1, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, "all", "all", 1, total_pages, lang=u_lang)

    try:
        await callback.message.edit_text(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer("🔄 Фільтри скинуто" if not is_en else "🔄 Filters reset")


@router.callback_query(F.data == "hist_back")
async def handle_hist_back(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    ctx = user.get("context_data", {}).get("history_filter", {})
    p_filter = ctx.get("printer", "all")
    d_filter = ctx.get("period", "all")
    page = int(ctx.get("page", 1))

    history = await app.storage.load_history()
    filtered = filter_history_records(history, app, p_filter, d_filter)
    PER_PAGE = 5
    total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))

    p_label, d_label = get_filter_labels(app, p_filter, d_filter, is_en)
    hist_txt = render_history_text(filtered, p_label, d_label, page, total_pages, is_en)
    ikb = get_history_inline_keyboard(app, p_filter, d_filter, page, total_pages, lang=u_lang)

    try:
        await callback.message.edit_text(hist_txt, parse_mode=ParseMode.HTML, reply_markup=ikb)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await callback.answer()


@router.callback_query(F.data == "hist_export_pdf")
async def handle_hist_export_pdf_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    await callback.answer("⏳ Генерація PDF..." if not is_en else "⏳ Generating PDF...")
    await export_history_pdf_impl(app, chat_id, callback.message, u_lang)


@router.callback_query(F.data == "hist_noop")
async def handle_hist_noop(callback: CallbackQuery):
    await callback.answer()


@router.message(
    F.text.lower().in_(
        [
            "📥 завантажити pdf звіт",
            "завантажити pdf звіт",
            "експорт pdf",
            "pdf",
            "звіт pdf",
            "/export_history",
            "/export",
            "/pdf_history",
            "/history_pdf",
            "📥 download pdf report",
            "download pdf report",
            "export pdf",
            "pdf report",
        ]
    )
)
async def handle_export_history_pdf(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    await export_history_pdf_impl(app, chat_id, message, u_lang)
