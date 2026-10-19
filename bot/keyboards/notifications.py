"""
Keyboard builders for notifications workflows.
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

def get_notification_inline_keyboard(printer_id: str) -> InlineKeyboardMarkup:
    """Builds interactive inline buttons attached to live printer notifications."""
    buttons = [
        [
            InlineKeyboardButton(text="📷 Фото", callback_data=f"notify_photo_{printer_id}"),
            InlineKeyboardButton(text="⏸ Пауза", callback_data=f"notify_pause_{printer_id}"),
            InlineKeyboardButton(text="💡 Світло", callback_data=f"notify_light_{printer_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_error_notification_inline_keyboard(printer_id: str) -> InlineKeyboardMarkup:
    """Builds interactive inline buttons attached to error and pause notifications."""
    buttons = [
        [
            InlineKeyboardButton(text="📷 Фото", callback_data=f"notify_photo_{printer_id}"),
            InlineKeyboardButton(text="▶️ Відновити", callback_data=f"notify_resume_{printer_id}"),
            InlineKeyboardButton(text="💡 Світло", callback_data=f"notify_light_{printer_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_finish_notification_inline_keyboard(printer_id: str) -> InlineKeyboardMarkup:
    """Builds interactive inline buttons attached to print finish and bed clear reminders."""
    buttons = [
        [
            InlineKeyboardButton(text="📸 Свіже фото столу", callback_data=f"notify_photo_{printer_id}"),
            InlineKeyboardButton(text="💡 Світло", callback_data=f"notify_light_{printer_id}"),
        ],
        [
            InlineKeyboardButton(text="🧹 Стіл очищено (Готовий)", callback_data=f"clear_bed_{printer_id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_maintenance_inline_keyboard(
    printer_id: str, item_key: str = "rails", item_name: str = "ТО"
) -> InlineKeyboardMarkup:
    """Inline keyboard attached to maintenance alerts to reset counter instantly."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"🧹 Провести {item_name} (Скинути)", callback_data=f"nmr:{printer_id[:12]}:{item_key}"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_notify_keyboard(u_notify: dict, lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    btn_start = ("✅ Print Start: On" if is_en else "✅ Початок друку: Вкл") if u_notify.get("start", True) else ("❌ Print Start: Off" if is_en else "❌ Початок друку: Викл")
    btn_finish = ("✅ Print Finish: On" if is_en else "✅ Закінчення друку: Вкл") if u_notify.get("finish", True) else ("❌ Закінчення друку: Викл")
    btn_pause = ("✅ Pause: On" if is_en else "✅ Пауза: Вкл") if u_notify.get("pause", True) else ("❌ Пауза: Викл")
    btn_hms = ("✅ HMS Errors: On" if is_en else "✅ HMS Помилки: Вкл") if u_notify.get("hms", True) else ("❌ HMS Errors: Off" if is_en else "❌ HMS Помилки: Викл")
    btn_clear = (
        ("✅ Clear Bed Alert: On" if is_en else "✅ Нагадування зняти деталь: Вкл")
        if u_notify.get("remind_clear", True)
        else ("❌ Clear Bed Alert: Off" if is_en else "❌ Нагадування зняти деталь: Викл")
    )

    try:
        t_val = int(u_notify.get("min_time_to_end", 0) or 0)
    except (TypeError, ValueError):
        t_val = 0

    try:
        f_val = int(u_notify.get("min_filament", 0) or 0)
    except (TypeError, ValueError):
        f_val = 0
    btn_time = f"⏳ {t_val} min before finish" if (is_en and t_val > 0) else (f"⏳ Повідомити за {t_val} хв до кінця" if t_val > 0 else "⏳ Сповіщення за N хв (Вимк)")
    btn_fil = f"📦 Filament < {f_val}g" if (is_en and f_val > 0) else (f"📦 Попередження нитки < {f_val}g" if f_val > 0 else "📦 Попередження нитки < Xg (Вимк)")

    cur_lang_label = "🇬🇧 English" if is_en else "🇺🇦 Українська"
    btn_lang = f"🌐 Мова / Language: {cur_lang_label}"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_start), KeyboardButton(text=btn_finish)],
            [KeyboardButton(text=btn_pause), KeyboardButton(text=btn_hms)],
            [KeyboardButton(text=btn_time), KeyboardButton(text=btn_fil)],
            [KeyboardButton(text=btn_clear), KeyboardButton(text=btn_lang)],
            [KeyboardButton(text="⬅️ Назад" if not is_en else "⬅️ Back")],
        ],
        resize_keyboard=True,
    )


def get_printer_select_notification_keyboard(printers: dict[str, Any], lang: str = "uk") -> InlineKeyboardMarkup:
    """Builds inline keyboard for selecting which printer's notification settings to configure."""
    is_en = lang == "en"
    buttons = []
    for p_id, p in printers.items():
        p_name = getattr(p, "name", "Printer")
        buttons.append([InlineKeyboardButton(text=f"🖨️ {p_name}", callback_data=f"pn_select:{p_id}")])
    buttons.append([InlineKeyboardButton(text="🌐 Глобальні сповіщення" if not is_en else "🌐 Global Preferences", callback_data="pn_select:global")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_printer_notification_inline_keyboard(printer: Any, lang: str = "uk") -> InlineKeyboardMarkup:
    """Builds per-printer notification controls inline keyboard matching WebApp structure."""
    is_en = lang == "en"
    p_notify = printer.get_notify_dict() if hasattr(printer, "get_notify_dict") and callable(getattr(printer, "get_notify_dict")) else {}
    if not isinstance(p_notify, dict):
        p_notify = {}
    p_id = printer.id

    start_icon = "✅" if p_notify.get("start", True) else "❌"
    finish_icon = "✅" if p_notify.get("finish", True) else "❌"
    pause_icon = "✅" if p_notify.get("pause", True) else "❌"
    hms_icon = "✅" if p_notify.get("hms", True) else "❌"
    clear_icon = "✅" if p_notify.get("remind_clear", True) else "❌"

    try:
        time_val = int(p_notify.get("min_time_to_end", 0) or 0)
    except (TypeError, ValueError):
        time_val = 0
    time_str = f"⏳ {time_val} хв" if time_val > 0 else "❌ Вимк"

    try:
        fil_val = int(p_notify.get("min_filament", 0) or 0)
    except (TypeError, ValueError):
        fil_val = 0
    fil_str = f"📦 <{fil_val}g" if fil_val > 0 else "❌ Вимк"

    maint_val = round(getattr(printer, "maintenance_hours_counter", 0.0), 1)

    buttons = [
        [InlineKeyboardButton(text=f"▶️ Початок друку: {start_icon}", callback_data=f"pn_toggle:{p_id}:start")],
        [InlineKeyboardButton(text=f"🏁 Закінчення друку: {finish_icon}", callback_data=f"pn_toggle:{p_id}:finish")],
        [InlineKeyboardButton(text=f"⏸️ Пауза друку: {pause_icon}", callback_data=f"pn_toggle:{p_id}:pause")],
        [InlineKeyboardButton(text=f"⚠️ HMS Помилки: {hms_icon}", callback_data=f"pn_toggle:{p_id}:hms")],
        [InlineKeyboardButton(text=f"🧹 Зняти деталь: {clear_icon}", callback_data=f"pn_toggle:{p_id}:remind_clear")],
        [InlineKeyboardButton(text=f"⏳ Таймер до кінця: {time_str}", callback_data=f"pn_cycle_time:{p_id}")],
        [InlineKeyboardButton(text=f"📦 Поріг нитки: {fil_str}", callback_data=f"pn_cycle_fil:{p_id}")],
        [InlineKeyboardButton(text=f"🔄 Скинути лічильник ТО ({maint_val}г)", callback_data=f"pn_reset_maint:{p_id}")],
        [InlineKeyboardButton(text="⬅️ Назад до принтерів" if not is_en else "⬅️ Back to Printers", callback_data="pn_back_list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
