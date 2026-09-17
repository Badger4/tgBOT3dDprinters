"""
Spool warehouse movements audit log and PDF export handlers with multi-level filtering.
"""

import html
import math
import time
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.keyboards import (
    get_filament_menu_keyboard,
    get_movements_action_filter_keyboard,
    get_movements_date_filter_keyboard,
    get_movements_filter_hub_keyboard,
    get_movements_spool_select_keyboard,
    get_spool_filter_keyboard,
    get_spool_movements_keyboard,
    get_warehouse_pdf_keyboard,
)
from utils.filament_utils import filter_spool_movements

router = Router()

ITEMS_PER_PAGE = 5

ACTION_MAP_UK = {
    "initial_stock": "📦 Внесення на склад",
    "refill": "➕ Поповнення",
    "manual_edit": "✏️ Ручне коригування",
    "write_off": "🗑️ Списання / Видалення",
    "print": "🖨️ Списання друком",
}

ACTION_MAP_EN = {
    "initial_stock": "📦 Initial Stock",
    "refill": "➕ Refill",
    "manual_edit": "✏️ Manual Edit",
    "write_off": "🗑️ Write-off",
    "print": "🖨️ Print Deduction",
}

DATE_MAP_UK = {
    "today": "Сьогодні",
    "yesterday": "Вчора",
    "week": "Останні 7 днів",
    "month": "Останні 30 днів",
    "all": "За весь час",
}

DATE_MAP_EN = {
    "today": "Today",
    "yesterday": "Yesterday",
    "week": "Last 7 days",
    "month": "Last 30 days",
    "all": "All time",
}


def get_user_mov_filters(user: dict) -> dict[str, Any]:
    """Retrieve or initialize active movement audit filters for the user."""
    ctx = user.setdefault("context_data", {})
    filt = ctx.setdefault("mov_filters", {})
    filt.setdefault("spool", "all")
    filt.setdefault("action", "all")
    filt.setdefault("date", "all")
    filt.setdefault("query", "")
    return filt


def format_movement_entry(m: dict, is_en: bool = False) -> str:
    dt = m.get("datetime") or time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("timestamp", 0)))
    spool_name = html.escape(str(m.get("spool_name") or "Котушка"))
    action_code = m.get("action", "")
    action_map = ACTION_MAP_EN if is_en else ACTION_MAP_UK
    action_label = action_map.get(action_code, f"⚡ {action_code}")
    ch_g = float(m.get("weight_change_g", 0.0))
    ch_sign = f"+{ch_g:.1f}" if ch_g > 0 else f"{ch_g:.1f}"
    prev_g = float(m.get("prev_weight_g", 0.0))
    new_g = float(m.get("new_weight_g", 0.0))
    reason = html.escape(str(m.get("reason") or ""))
    user = html.escape(str(m.get("user") or "System"))

    txt = f"• 📅 <b>{dt}</b> — 🧵 <b>{spool_name}</b>\n"
    txt += f"   {action_label} | <b>{ch_sign}g</b> ({prev_g:.0f}g ➔ <b>{new_g:.0f}g</b>)\n"
    if reason:
        txt += f"   📝 <i>{reason}</i> (👤 {user})\n"
    return txt


def build_movements_page_text(
    movements: list[dict],
    page: int,
    spool_filter: str = "all",
    spool_name_filter: str = "",
    filters: dict[str, Any] | None = None,
    is_en: bool = False,
) -> tuple[str, int]:
    filters = filters or {}
    total_count = len(movements)

    # Build active filter badge strings
    badges = []
    active_spool = filters.get("spool", spool_filter)
    if active_spool != "all" and spool_name_filter:
        badges.append(f"🧵 {html.escape(spool_name_filter)}")

    active_date = filters.get("date", "all")
    if active_date != "all":
        d_map = DATE_MAP_EN if is_en else DATE_MAP_UK
        badges.append(f"📅 {d_map.get(active_date, active_date)}")

    active_act = filters.get("action", "all")
    if active_act != "all":
        a_map = ACTION_MAP_EN if is_en else ACTION_MAP_UK
        badges.append(a_map.get(active_act, active_act))

    active_query = str(filters.get("query", "")).strip()
    if active_query:
        badges.append(f'🔍 "{html.escape(active_query)}"')

    has_filters = len(badges) > 0 or (spool_filter != "all" and bool(spool_name_filter))

    if total_count == 0:
        if has_filters:
            filter_summary = " | ".join(badges) if badges else f"🧵 {html.escape(spool_name_filter)}"
            msg = (
                f"🔍 <b>{'Movement Audit' if is_en else 'Аудит руху'}:</b>\n\n"
                f"ℹ️ {'No movements found matching the active filters' if is_en else 'Не знайдено записів руху за обраними фільтрами'}:\n"
                f"<b>{filter_summary}</b>\n\n"
                f"<i>{'Click \"Filter\" below to adjust criteria or \"Clear\" to view all records.' if is_en else 'Натисніть «Фільтри» нижче щоб змінити критерії або «Скинути» для показу всіх записів.'}</i>"
            )
        else:
            msg = (
                "📜 <b>Warehouse Movements Audit Log</b>\n\n"
                "ℹ️ <i>Audit log is currently empty. Any warehouse operations (adding, refilling, printing, write-offs) will be recorded here automatically.</i>"
                if is_en
                else "📜 <b>Журнал аудиту руху матеріалів складу</b>\n\n"
                "ℹ️ <i>Журнал аудиту наразі порожній. Будь-які операції (додавання, поповнення, друк, списання) фіксуватимуться тут автоматично.</i>"
            )
        return msg, 1

    total_pages = max(1, math.ceil(total_count / ITEMS_PER_PAGE))
    page = max(0, min(page, total_pages - 1))

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = movements[start_idx:end_idx]

    filter_info = ""
    if badges:
        filter_label = "Filters" if is_en else "Фільтри"
        filter_info = f"\n🔍 <b>{filter_label}:</b> {' | '.join(badges)}"
    elif spool_filter != "all" and spool_name_filter:
        filter_info = f"\n🔍 <b>{'Filter' if is_en else 'Фільтр'}:</b> 🧵 <b>{html.escape(spool_name_filter)}</b>"

    header = (
        f"📜 <b>Журнал аудиту руху матеріалів складу</b>{filter_info}\n"
        f"📊 Загалом записів: <b>{total_count}</b> | Стор. <b>{page + 1}/{total_pages}</b>\n\n"
        if not is_en
        else f"📜 <b>Warehouse Movements Audit Log</b>{filter_info}\n"
        f"📊 Total records: <b>{total_count}</b> | Page <b>{page + 1}/{total_pages}</b>\n\n"
    )

    body = "\n".join(format_movement_entry(m, is_en=is_en) for m in page_items)
    return f"{header}{body}", total_pages


async def render_movements_page(
    chat_id: str,
    app,
    page: int = 0,
    callback: CallbackQuery | None = None,
    message: Message | None = None,
):
    """Unified rendering routine for movements log page with active filters."""
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    all_movements = await app.storage.load_spool_movements()
    spools = await app.storage.load_spools()

    spool_id_filter = filters.get("spool", "all")
    spool_name_filter = ""
    if spool_id_filter != "all":
        spool_name_filter = spools.get(spool_id_filter, {}).get("name", spool_id_filter)

    filtered = filter_spool_movements(
        all_movements,
        spool_id=spool_id_filter,
        action=filters.get("action", "all"),
        date_range=filters.get("date", "all"),
        query=filters.get("query", ""),
    )

    text, total_pages = build_movements_page_text(
        filtered,
        page=page,
        spool_filter=spool_id_filter,
        spool_name_filter=spool_name_filter,
        filters=filters,
        is_en=is_en,
    )
    kb = get_spool_movements_keyboard(
        page=page,
        total_pages=total_pages,
        spool_filter=spool_id_filter,
        lang=u_lang,
        active_filters=filters,
    )

    if callback and callback.message:
        try:
            await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
    elif message:
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.message(
    F.text.lower().in_(
        [
            "📜 аудит руху",
            "аудит руху",
            "📜 аудит",
            "аудит",
            "📜 movement audit",
            "movement audit",
            "movement log",
            "audit log",
            "audit",
        ]
    )
)
async def handle_spool_movements_view(message: Message, app, state: FSMContext | None = None):
    if state:
        await state.clear()
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    if user.get("state") == "awaiting_mov_search":
        user["state"] = "idle"
        await app.storage.save_user(user)

    await render_movements_page(chat_id=chat_id, app=app, page=0, message=message)


@router.callback_query(F.data.startswith("mov_page:"))
async def handle_movements_page_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    await render_movements_page(chat_id=chat_id, app=app, page=page, callback=callback)
    await callback.answer()


@router.callback_query(F.data == "mov_filter_menu")
async def handle_movements_filter_hub_callback(callback: CallbackQuery, app):
    """Renders the filter hub menu showing current selections."""
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    spools = await app.storage.load_spools()
    spool_name = ""
    if filters.get("spool", "all") != "all":
        spool_name = spools.get(filters["spool"], {}).get("name", filters["spool"])

    d_val = filters.get("date", "all")
    d_map = DATE_MAP_EN if is_en else DATE_MAP_UK
    d_txt = d_map.get(d_val, "За весь час" if not is_en else "All time")

    a_val = filters.get("action", "all")
    a_map = ACTION_MAP_EN if is_en else ACTION_MAP_UK
    a_txt = a_map.get(a_val, "Всі операції" if not is_en else "All actions")

    s_txt = spool_name if spool_name else ("Всі котушки" if not is_en else "All spools")
    q_txt = filters.get("query", "").strip() or ("— (немає)" if not is_en else "— (none)")

    msg_text = (
        "🔍 <b>Панель фільтрів аудиту руху:</b>\n\n"
        f"• 🧵 <b>Котушка:</b> {html.escape(s_txt)}\n"
        f"• 📅 <b>Період:</b> {d_txt}\n"
        f"• ⚡ <b>Операція:</b> {a_txt}\n"
        f"• 🔍 <b>Пошук:</b> <i>{html.escape(q_txt)}</i>\n\n"
        "<i>Натисніть кнопку нижче, щоб налаштувати відповідний критерій:</i>"
        if not is_en
        else "🔍 <b>Movement Audit Filter Hub:</b>\n\n"
        f"• 🧵 <b>Spool:</b> {html.escape(s_txt)}\n"
        f"• 📅 <b>Date Range:</b> {d_txt}\n"
        f"• ⚡ <b>Action Type:</b> {a_txt}\n"
        f"• 🔍 <b>Search Text:</b> <i>{html.escape(q_txt)}</i>\n\n"
        "<i>Select an option below to adjust criteria:</i>"
    )

    kb = get_movements_filter_hub_keyboard(filters, spool_name=spool_name, lang=u_lang)
    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "mov_f_date_menu")
async def handle_movements_date_submenu(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    kb = get_movements_date_filter_keyboard(current_date=filters.get("date", "all"), lang=u_lang)
    msg_text = (
        "📅 <b>Оберіть період часу для фільтрації записів:</b>"
        if not is_en
        else "📅 <b>Select date range for filtering records:</b>"
    )
    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("mov_f_set_date:"))
async def handle_movements_set_date(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    date_code = callback.data.split(":", 1)[1]
    filters["date"] = date_code
    await app.storage.save_user(user)

    # Return to filter hub
    await handle_movements_filter_hub_callback(callback, app)


@router.callback_query(F.data == "mov_f_action_menu")
async def handle_movements_action_submenu(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    kb = get_movements_action_filter_keyboard(current_action=filters.get("action", "all"), lang=u_lang)
    msg_text = (
        "⚡ <b>Оберіть тип операції для фільтрації:</b>"
        if not is_en
        else "⚡ <b>Select action type for filtering:</b>"
    )
    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("mov_f_set_act:"))
async def handle_movements_set_action(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    act_code = callback.data.split(":", 1)[1]
    filters["action"] = act_code
    await app.storage.save_user(user)

    # Return to filter hub
    await handle_movements_filter_hub_callback(callback, app)


@router.callback_query(F.data.startswith("mov_f_spool_menu:") | F.data.startswith("mov_f_spool_page:"))
async def handle_movements_spool_submenu(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

    spools = await app.storage.load_spools()
    kb = get_movements_spool_select_keyboard(
        spools,
        current_spool=filters.get("spool", "all"),
        page=page,
        lang=u_lang,
    )
    msg_text = (
        "🧵 <b>Оберіть котушку зі складу для фільтрації:</b>"
        if not is_en
        else "🧵 <b>Select spool from stock to filter:</b>"
    )
    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("mov_f_set_spool:"))
async def handle_movements_set_spool(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    spool_code = callback.data.split(":", 1)[1]
    filters["spool"] = spool_code
    await app.storage.save_user(user)

    # Return to filter hub
    await handle_movements_filter_hub_callback(callback, app)


@router.callback_query(F.data == "mov_f_search_prompt")
async def handle_movements_search_prompt(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    user["state"] = "awaiting_mov_search"
    await app.storage.save_user(user)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Очистити пошук" if not is_en else "❌ Clear search",
                    callback_data="mov_f_clear_search",
                ),
                InlineKeyboardButton(
                    text="⬅️ До фільтрів" if not is_en else "⬅️ Back to filters",
                    callback_data="mov_filter_menu",
                ),
            ]
        ]
    )

    msg_text = (
        "🔍 <b>Пошук по журналу аудиту руху</b>\n\n"
        "Надішліть у чат текстове повідомлення з ключовим словом (назва моделі/деталі, причина коригування, ім'я користувача або назва котушки).\n\n"
        "<i>Для скасування або очищення пошуку натисніть кнопку нижче або надішліть «скинути».</i>"
        if not is_en
        else "🔍 <b>Search movements audit log</b>\n\n"
        "Send a message with your search keyword (model name, correction reason, user name, or spool name).\n\n"
        "<i>To cancel or clear search, click below or send \"clear\".</i>"
    )

    try:
        if callback.message:
            await callback.message.edit_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=cancel_kb)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "mov_f_clear_search")
async def handle_movements_clear_search(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    filters = get_user_mov_filters(user)

    filters["query"] = ""
    user["state"] = "idle"
    await app.storage.save_user(user)

    await callback.answer("🔍 Пошук очищено" if u_lang != "en" else "🔍 Search cleared")
    await handle_movements_filter_hub_callback(callback, app)


async def mov_search_state_filter(message: Message, app) -> bool:
    if not message.text:
        return False
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    return user.get("state") == "awaiting_mov_search"


@router.message(mov_search_state_filter)
async def handle_movements_search_input(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    raw_text = (message.text or "").strip()
    if raw_text.lower() in ["❌", "скасувати", "cancel", "скинути", "clear", "-", "none"]:
        filters["query"] = ""
    else:
        filters["query"] = raw_text

    user["state"] = "idle"
    await app.storage.save_user(user)

    # Render filtered log
    await render_movements_page(chat_id=chat_id, app=app, page=0, message=message)


@router.callback_query(F.data.in_(["mov_f_clear", "mov_filter_clear"]))
async def handle_movements_filter_clear_all(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    filters["spool"] = "all"
    filters["action"] = "all"
    filters["date"] = "all"
    filters["query"] = ""
    user["state"] = "idle"
    await app.storage.save_user(user)

    await callback.answer("✅ Всі фільтри скинуто" if not is_en else "✅ All filters reset")
    await render_movements_page(chat_id=chat_id, app=app, page=0, callback=callback)


@router.callback_query(F.data == "mov_f_back")
async def handle_movements_back_to_log(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    await render_movements_page(chat_id=chat_id, app=app, page=0, callback=callback)
    await callback.answer()


@router.callback_query(F.data.startswith("mov_spool_direct:"))
async def handle_movements_spool_direct(callback: CallbackQuery, app):
    """Direct jump to movements log pre-filtered for a specific spool."""
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    target_spool = callback.data.split(":", 1)[1]
    filters["spool"] = target_spool
    filters["action"] = "all"
    filters["date"] = "all"
    filters["query"] = ""
    user["state"] = "idle"
    await app.storage.save_user(user)

    await render_movements_page(chat_id=chat_id, app=app, page=0, callback=callback)
    await callback.answer()


@router.callback_query(F.data.startswith("mov_filter:"))
async def handle_legacy_mov_filter(callback: CallbackQuery, app):
    """Backward compatibility for legacy spool filter callbacks."""
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    filters = get_user_mov_filters(user)

    spool_code = callback.data.split(":", 1)[1]
    filters["spool"] = spool_code
    await app.storage.save_user(user)

    await render_movements_page(chat_id=chat_id, app=app, page=0, callback=callback)
    await callback.answer()


@router.message(
    F.text.lower().in_(
        [
            "📄 експорт pdf",
            "експорт pdf",
            "📄 pdf",
            "📄 export pdf",
            "export pdf",
        ]
    )
)
async def handle_export_warehouse_pdf_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    kb = get_warehouse_pdf_keyboard(lang=u_lang)
    msg_txt = (
        "📄 <b>Експорт звітів складу в PDF</b>\n\n"
        "Оберіть необхідний тип документа для завантаження:"
        if not is_en
        else "📄 <b>Warehouse PDF Export</b>\n\n"
        "Select the report type you wish to download:"
    )
    await message.answer(msg_txt, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(F.data.in_(["mov_export_pdf", "pdf_export_movements"]))
async def handle_export_movements_pdf_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"
    filters = get_user_mov_filters(user)

    await callback.answer("⏳ Формування PDF звіту..." if not is_en else "⏳ Generating PDF report...")
    try:
        all_movements = await app.storage.load_spool_movements()
        spools = await app.storage.load_spools()

        spool_name = ""
        if filters.get("spool", "all") != "all":
            spool_name = spools.get(filters["spool"], {}).get("name", filters["spool"])

        filtered = filter_spool_movements(
            all_movements,
            spool_id=filters.get("spool", "all"),
            action=filters.get("action", "all"),
            date_range=filters.get("date", "all"),
            query=filters.get("query", ""),
        )

        subtitles = []
        if filters.get("spool", "all") != "all" and spool_name:
            subtitles.append(f"Котушка: {spool_name}" if not is_en else f"Spool: {spool_name}")
        if filters.get("date", "all") != "all":
            d_map = DATE_MAP_EN if is_en else DATE_MAP_UK
            subtitles.append(f"Період: {d_map.get(filters['date'])}" if not is_en else f"Period: {d_map.get(filters['date'])}")
        if filters.get("action", "all") != "all":
            a_map = ACTION_MAP_EN if is_en else ACTION_MAP_UK
            subtitles.append(f"Операція: {a_map.get(filters['action'])}" if not is_en else f"Action: {a_map.get(filters['action'])}")
        if filters.get("query", "").strip():
            subtitles.append(f'Пошук: "{filters["query"].strip()}"' if not is_en else f'Search: "{filters["query"].strip()}"')

        filter_sub = " | ".join(subtitles) if subtitles else None

        from services.report_generator import generate_movements_pdf_report
        pdf_bytes = generate_movements_pdf_report(filtered, filter_subtitle=filter_sub)

        filename = f"spool_movements_audit_{int(time.time())}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=filename)
        cap = (
            f"📜 <b>Журнал аудиту руху матеріалів складу (PDF)</b>"
            f"{f' — {filter_sub}' if filter_sub else ''}"
            if not is_en
            else f"📜 <b>Warehouse Movements Audit Log (PDF)</b>"
            f"{f' — {filter_sub}' if filter_sub else ''}"
        )
        if callback.message:
            await callback.message.answer_document(doc, caption=cap, parse_mode=ParseMode.HTML)
        elif callback.bot:
            await callback.bot.send_document(chat_id=callback.from_user.id, document=doc, caption=cap, parse_mode=ParseMode.HTML)
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "pdf_export_spools")
async def handle_export_spools_pdf_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    await callback.answer("⏳ Формування PDF звіту..." if not is_en else "⏳ Generating PDF report...")
    try:
        spools = await app.storage.load_spools()
        from services.report_generator import generate_spools_pdf_report
        pdf_bytes = generate_spools_pdf_report(spools, printers=getattr(app, "printers", None))

        filename = f"spools_inventory_{int(time.time())}.pdf"
        doc = BufferedInputFile(pdf_bytes, filename=filename)
        cap = (
            "📦 <b>Звіт залишків котушок на складі (PDF)</b>"
            if not is_en
            else "📦 <b>Spool Stock Inventory Report (PDF)</b>"
        )
        if callback.message:
            await callback.message.answer_document(doc, caption=cap, parse_mode=ParseMode.HTML)
        elif callback.bot:
            await callback.bot.send_document(chat_id=callback.from_user.id, document=doc, caption=cap, parse_mode=ParseMode.HTML)
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "pdf_export_both")
async def handle_export_both_pdfs_callback(callback: CallbackQuery, app):
    chat_id = str(callback.message.chat.id) if callback.message else str(callback.from_user.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    await callback.answer("⏳ Формування PDF звітів..." if not is_en else "⏳ Generating PDF reports...")
    try:
        spools = await app.storage.load_spools()
        movements = await app.storage.load_spool_movements()
        from services.report_generator import generate_movements_pdf_report, generate_spools_pdf_report

        doc_spools = BufferedInputFile(
            generate_spools_pdf_report(spools, printers=getattr(app, "printers", None)),
            filename=f"spools_inventory_{int(time.time())}.pdf",
        )
        doc_movements = BufferedInputFile(
            generate_movements_pdf_report(movements),
            filename=f"spool_movements_audit_{int(time.time())}.pdf",
        )

        if callback.message:
            await callback.message.answer_document(
                doc_spools,
                caption="📦 <b>Звіт залишків котушок на складі (PDF)</b>" if not is_en else "📦 <b>Spool Stock Inventory Report (PDF)</b>",
                parse_mode=ParseMode.HTML,
            )
            await callback.message.answer_document(
                doc_movements,
                caption="📜 <b>Журнал аудиту руху матеріалів складу (PDF)</b>" if not is_en else "📜 <b>Warehouse Movements Audit Log (PDF)</b>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        if callback.message:
            await callback.message.answer(f"⚠️ Помилка формування PDF: {e}")


@router.callback_query(F.data == "mov_noop")
async def handle_mov_noop(callback: CallbackQuery):
    await callback.answer()
