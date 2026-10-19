"""
Keyboard builders for history workflows.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from config import WEBAPP_URL
from models.printer import BambuPrinter
from utils.filament_utils import get_color_emoji
from utils.i18n import t

def get_history_inline_keyboard(
    app,
    printer_filter: str = "all",
    date_filter: str = "all",
    page: int = 1,
    total_pages: int = 1,
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    is_en = lang == "en"
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

    p_btn_text = f"🖨️ {p_label[:14]}.. ▾" if len(p_label) > 16 else f"🖨️ {p_label} ▾"
    d_btn_text = f"📅 {d_label} ▾"

    keyboard = [
        [
            InlineKeyboardButton(text=p_btn_text, callback_data="hist_menu_p"),
            InlineKeyboardButton(text=d_btn_text, callback_data="hist_menu_d"),
        ]
    ]

    if total_pages > 1:
        pag_row = []
        if page > 1:
            pag_row.append(InlineKeyboardButton(text="◀️", callback_data=f"hist_page:{page - 1}"))
        else:
            pag_row.append(InlineKeyboardButton(text="▪️", callback_data="hist_noop"))

        pag_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="hist_noop"))

        if page < total_pages:
            pag_row.append(InlineKeyboardButton(text="▶️", callback_data=f"hist_page:{page + 1}"))
        else:
            pag_row.append(InlineKeyboardButton(text="▪️", callback_data="hist_noop"))
        keyboard.append(pag_row)

    action_row = []
    if printer_filter != "all" or date_filter != "all":
        action_row.append(InlineKeyboardButton(text="🔄 Reset" if is_en else "🔄 Скинути", callback_data="hist_reset"))

    action_row.append(InlineKeyboardButton(text="📥 PDF Report" if is_en else "📥 PDF звіт", callback_data="hist_export_pdf"))
    keyboard.append(action_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_history_printer_filter_keyboard(
    app,
    current_filter: str = "all",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    buttons = []
    all_check = " ✅" if current_filter == "all" else ""
    buttons.append([InlineKeyboardButton(text=f"🌐 {'All printers' if is_en else 'Усі принтери'}{all_check}", callback_data="hist_p:all")])

    printers = list(app.printers.values()) if hasattr(app, "printers") and app.printers else []
    for p in printers:
        p_check = " ✅" if str(p.id) == str(current_filter) else ""
        buttons.append([InlineKeyboardButton(text=f"🖨️ {p.name}{p_check}", callback_data=f"hist_p:{p.id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ " + ("Back to history" if is_en else "Назад до історії"), callback_data="hist_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_history_date_filter_keyboard(
    current_filter: str = "all",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    periods = [
        ("all", "🌐 " + ("All time" if is_en else "Увесь час")),
        ("today", "📅 " + ("Today" if is_en else "Сьогодні")),
        ("7d", "📅 " + ("Last 7 days" if is_en else "Останні 7 днів")),
        ("30d", "📅 " + ("Last 30 days" if is_en else "Останні 30 днів")),
    ]
    buttons = []
    for code, title in periods:
        check = " ✅" if current_filter == code else ""
        buttons.append([InlineKeyboardButton(text=f"{title}{check}", callback_data=f"hist_d:{code}")])

    buttons.append([InlineKeyboardButton(text="⬅️ " + ("Back to history" if is_en else "Назад до історії"), callback_data="hist_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_spool_movements_keyboard(
    page: int,
    total_pages: int,
    spool_filter: str = "all",
    lang: str = "uk",
    active_filters: dict[str, Any] | None = None,
) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []

    filters = active_filters or {}
    has_active_filters = (
        (spool_filter != "all" and spool_filter)
        or (filters.get("spool", "all") not in ["all", ""])
        or (filters.get("action", "all") not in ["all", ""])
        or (filters.get("date", "all") not in ["all", ""])
        or bool(filters.get("query", ""))
    )

    # Count active filter dimensions
    active_count = 0
    if filters.get("spool", "all") not in ["all", ""] or (spool_filter != "all" and spool_filter):
        active_count += 1
    if filters.get("action", "all") not in ["all", ""]:
        active_count += 1
    if filters.get("date", "all") not in ["all", ""]:
        active_count += 1
    if filters.get("query", ""):
        active_count += 1

    filt_btn_text = f"🔍 Фільтри ({active_count})" if active_count > 0 else ("🔍 Filter" if is_en else "🔍 Фільтри")
    pdf_label = "📥 PDF Аудит" if not is_en else "📥 PDF Audit"

    if has_active_filters:
        clear_label = "❌ Скинути" if not is_en else "❌ Clear"
        keyboard.append([
            InlineKeyboardButton(text=filt_btn_text, callback_data="mov_filter_menu"),
            InlineKeyboardButton(text=clear_label, callback_data="mov_f_clear"),
        ])
        keyboard.append([
            InlineKeyboardButton(text=pdf_label, callback_data="mov_export_pdf"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text=filt_btn_text, callback_data="mov_filter_menu"),
            InlineKeyboardButton(text=pdf_label, callback_data="mov_export_pdf"),
        ])

    # Pagination row
    if total_pages > 1:
        pag_row = []
        if page > 0:
            pag_row.append(InlineKeyboardButton(text="◀️", callback_data=f"mov_page:{page - 1}:{spool_filter}"))
        else:
            pag_row.append(InlineKeyboardButton(text="▪️", callback_data="mov_noop"))

        pag_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="mov_noop"))

        if page < total_pages - 1:
            pag_row.append(InlineKeyboardButton(text="▶️", callback_data=f"mov_page:{page + 1}:{spool_filter}"))
        else:
            pag_row.append(InlineKeyboardButton(text="▪️", callback_data="mov_noop"))

        keyboard.append(pag_row)

    # Refresh row
    keyboard.append([
        InlineKeyboardButton(text="🔄 " + ("Refresh" if is_en else "Оновити"), callback_data=f"mov_page:{page}:{spool_filter}")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_movements_filter_hub_keyboard(
    filters: dict[str, Any],
    spool_name: str = "",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    """Renders the main filter configuration hub for warehouse movements audit."""
    is_en = lang == "en"
    keyboard = []

    # 1. Spool row
    sp_val = filters.get("spool", "all")
    if sp_val != "all" and spool_name:
        s_title = f"🧵 {spool_name[:16]}..." if len(spool_name) > 16 else f"🧵 {spool_name}"
    else:
        s_title = "🧵 Всі котушки" if not is_en else "🧵 All spools"
    keyboard.append([InlineKeyboardButton(text=s_title, callback_data="mov_f_spool_menu:0")])

    # 2. Date & Action row
    date_val = filters.get("date", "all")
    date_map = {
        "today": "Сьогодні" if not is_en else "Today",
        "yesterday": "Вчора" if not is_en else "Yesterday",
        "week": "7 днів" if not is_en else "7 days",
        "month": "30 днів" if not is_en else "30 days",
        "all": "Весь час" if not is_en else "All time",
    }
    d_label = f"📅 {date_map.get(date_val, 'Весь час')}"

    act_val = filters.get("action", "all")
    act_map = {
        "print": "🖨️ Друк",
        "manual_edit": "✏️ Коригування",
        "initial_stock": "📦 Внесення",
        "refill": "➕ Поповнення",
        "write_off": "🗑️ Списання",
        "all": "⚡ Всі дії" if not is_en else "⚡ All actions",
    }
    a_label = f"{act_map.get(act_val, '⚡ Всі дії')}"
    keyboard.append([
        InlineKeyboardButton(text=d_label, callback_data="mov_f_date_menu"),
        InlineKeyboardButton(text=a_label, callback_data="mov_f_action_menu"),
    ])

    # 3. Search query row
    q_val = filters.get("query", "").strip()
    if q_val:
        q_label = f"🔍 Пошук: '{q_val[:12]}'"
    else:
        q_label = "🔍 Пошук за назвою..." if not is_en else "🔍 Search query..."
    keyboard.append([InlineKeyboardButton(text=q_label, callback_data="mov_f_search_prompt")])

    # 4. Actions row: Reset all & Return
    keyboard.append([
        InlineKeyboardButton(text="❌ Скинути всі" if not is_en else "❌ Clear all", callback_data="mov_f_clear"),
        InlineKeyboardButton(text="⬅️ До журналу" if not is_en else "⬅️ Back to log", callback_data="mov_f_back"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_movements_date_filter_keyboard(
    current_date: str = "all",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    """Filter choices for date ranges."""
    is_en = lang == "en"
    dates = [
        ("all", "🌐 За весь час" if not is_en else "🌐 All time"),
        ("today", "📅 Сьогодні" if not is_en else "📅 Today"),
        ("yesterday", "📅 Вчора" if not is_en else "📅 Yesterday"),
        ("week", "📅 Останні 7 днів" if not is_en else "📅 Last 7 days"),
        ("month", "📅 Останні 30 днів" if not is_en else "📅 Last 30 days"),
    ]
    keyboard = []
    for code, label in dates:
        mark = " ✅" if code == current_date else ""
        keyboard.append([InlineKeyboardButton(text=f"{label}{mark}", callback_data=f"mov_f_set_date:{code}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад до фільтрів" if not is_en else "⬅️ Back to filters", callback_data="mov_filter_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_movements_action_filter_keyboard(
    current_action: str = "all",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    """Filter choices for movement action types."""
    is_en = lang == "en"
    actions = [
        ("all", "🌐 Всі операції" if not is_en else "🌐 All actions"),
        ("print", "🖨️ Тільки друк" if not is_en else "🖨️ Print only"),
        ("manual_edit", "✏️ Ручне коригування" if not is_en else "✏️ Manual edit"),
        ("initial_stock", "📦 Внесення на склад" if not is_en else "📦 Initial stock"),
        ("refill", "➕ Поповнення запасу" if not is_en else "➕ Refill"),
        ("write_off", "🗑️ Списання / Видалення" if not is_en else "🗑️ Write-off"),
    ]
    keyboard = []
    for code, label in actions:
        mark = " ✅" if code == current_action else ""
        keyboard.append([InlineKeyboardButton(text=f"{label}{mark}", callback_data=f"mov_f_set_act:{code}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад до фільтрів" if not is_en else "⬅️ Back to filters", callback_data="mov_filter_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_movements_spool_select_keyboard(
    spools: dict[str, dict[str, Any]],
    current_spool: str = "all",
    page: int = 0,
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    """2-column paginated spool selector for audit filtering."""
    from utils.filament_utils import get_color_emoji
    is_en = lang == "en"
    keyboard = []

    # All spools button
    all_mark = " ✅" if current_spool == "all" else ""
    keyboard.append([InlineKeyboardButton(text=f"🌐 {'All spools' if is_en else 'Всі котушки'}{all_mark}", callback_data="mov_f_set_spool:all")])

    spool_items = list(spools.items())
    per_page = 6
    total_pages = max(1, (len(spool_items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    page_spools = spool_items[page * per_page : (page + 1) * per_page]

    # Grid 2 per row
    row = []
    for s_id, s in page_spools:
        s_name = str(s.get("name", "Spool"))
        short_name = s_name[:14] + "…" if len(s_name) > 15 else s_name
        s_color = s.get("color_name") or s.get("color", "")
        ico = get_color_emoji(s_color)
        mark = " ✅" if str(s_id) == str(current_spool) else ""
        btn_text = f"{ico} {short_name}{mark}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"mov_f_set_spool:{s_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Pagination row
    if total_pages > 1:
        p_row = []
        if page > 0:
            p_row.append(InlineKeyboardButton(text="◀️", callback_data=f"mov_f_spool_page:{page - 1}"))
        else:
            p_row.append(InlineKeyboardButton(text="▪️", callback_data="mov_noop"))
        p_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="mov_noop"))
        if page < total_pages - 1:
            p_row.append(InlineKeyboardButton(text="▶️", callback_data=f"mov_f_spool_page:{page + 1}"))
        else:
            p_row.append(InlineKeyboardButton(text="▪️", callback_data="mov_noop"))
        keyboard.append(p_row)

    keyboard.append([InlineKeyboardButton(text="⬅️ Назад до фільтрів" if not is_en else "⬅️ Back to filters", callback_data="mov_filter_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
