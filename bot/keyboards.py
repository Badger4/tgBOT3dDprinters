"""
Reply and Inline keyboard builders for Telegram Bot.
"""

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL
from models.printer import BambuPrinter


def get_main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    keyboard = []
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        keyboard.append([KeyboardButton(text="📱 Відкрити WebApp 🚀", web_app=WebAppInfo(url=WEBAPP_URL))])

    keyboard.extend(
        [
            [KeyboardButton(text="🖨️ Принтери"), KeyboardButton(text="📊 Стан ферми")],
            [KeyboardButton(text="📦 Склад"), KeyboardButton(text="💰 Комерція")],
            [KeyboardButton(text="🔔 Налаштування сповіщень")],
        ]
    )
    if is_admin:
        keyboard.append([KeyboardButton(text="👑 Адмінка")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_webapp_inline_keyboard() -> InlineKeyboardMarkup:
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        btn = InlineKeyboardButton(text="📱 Відкрити WebApp 🚀", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        btn = InlineKeyboardButton(
            text="🌐 Відкрити WebApp в браузері 🚀", url=WEBAPP_URL or "http://localhost:8080/webapp"
        )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def get_printers_keyboard(printers: dict[str, BambuPrinter]) -> ReplyKeyboardMarkup:
    keyboard = []
    for p in printers.values():
        keyboard.append([KeyboardButton(text=f"🖨️ {p.name}")])
    keyboard.append([KeyboardButton(text="➕ Додати принтер")])
    keyboard.append([KeyboardButton(text="Головне меню")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_printer_menu_keyboard(printer: BambuPrinter) -> ReplyKeyboardMarkup:
    notify_str = "🔔 Сповіщення: Включено" if printer.notify else "🔕 Сповіщення: Виключено"

    keyboard = [
        [KeyboardButton(text="📊 Статус"), KeyboardButton(text="📷 Камера")],
        [KeyboardButton(text="🎛️ Керування принтером"), KeyboardButton(text="🧵 Філамент")],
        [KeyboardButton(text="🎯 Калібрувати"), KeyboardButton(text=notify_str)],
        [KeyboardButton(text="🧹 Скинути лічильник ТО"), KeyboardButton(text="🗑️ Видалити принтер")],
        [KeyboardButton(text="🖨️ Назад до принтерів")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


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


def get_maintenance_inline_keyboard(
    printer_id: str, item_key: str = "rails", item_name: str = "ТО"
) -> InlineKeyboardMarkup:
    """Inline keyboard attached to maintenance alerts to reset counter instantly."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"🧹 Провести {item_name} (Скинути)", callback_data=f"notify_maint_reset_{printer_id}_{item_key}"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deduct_weight_inline_keyboard(printer_id: str) -> InlineKeyboardMarkup:
    """Builds interactive inline buttons to let user manually select deducted weight."""
    buttons = [
        [
            InlineKeyboardButton(text="2g", callback_data=f"deduct_w_{printer_id}_2"),
            InlineKeyboardButton(text="5g", callback_data=f"deduct_w_{printer_id}_5"),
            InlineKeyboardButton(text="10g", callback_data=f"deduct_w_{printer_id}_10"),
            InlineKeyboardButton(text="15g", callback_data=f"deduct_w_{printer_id}_15"),
        ],
        [
            InlineKeyboardButton(text="25g", callback_data=f"deduct_w_{printer_id}_25"),
            InlineKeyboardButton(text="50g", callback_data=f"deduct_w_{printer_id}_50"),
            InlineKeyboardButton(text="100g", callback_data=f"deduct_w_{printer_id}_100"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_printer_control_keyboard(printer: BambuPrinter) -> ReplyKeyboardMarkup:
    pause_resume_btn = (
        KeyboardButton(text="▶️ Відновити друк") if printer.gcode_state == "PAUSE" else KeyboardButton(text="⏸️ Пауза")
    )
    keyboard = [
        [KeyboardButton(text="⚡ Швидкість"), KeyboardButton(text="💡 Підсвітка")],
        [KeyboardButton(text="⏹️ Зупинити друк"), pause_resume_btn],
        [KeyboardButton(text="⬅️ Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="👥 Користувачі")],
        [KeyboardButton(text="🆕 Нові користувачі")],
        [KeyboardButton(text="Головне меню")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spool_presets_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="⚫ Bambu PLA Black (850 грн)", callback_data="spool_preset_bambu_pla_black"),
            InlineKeyboardButton(text="⚪ Sunlu PLA White (650 грн)", callback_data="spool_preset_sunlu_pla_white"),
        ],
        [
            InlineKeyboardButton(text="🩶 eSUN PETG Grey (700 грн)", callback_data="spool_preset_esun_petg_grey"),
            InlineKeyboardButton(text="🔴 TPU 95A Red (950 грн)", callback_data="spool_preset_tpu_red"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_filament_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="➕ Нова котушка"), KeyboardButton(text="🔗 Встановити на принтер")],
        [KeyboardButton(text="🔓 Зняти з принтера"), KeyboardButton(text="✏️ Редагувати котушку")],
        [KeyboardButton(text="✏️ Ручне введення ваги"), KeyboardButton(text="🗑️ Видалити котушку")],
        [KeyboardButton(text="⬅️ Назад")],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spools_keyboard(spools: dict[str, dict[str, Any]]) -> ReplyKeyboardMarkup:
    keyboard = []
    for s_id, s in spools.items():
        name = s.get("name", "Котушка")
        grams = s.get("remaining_grams", 1000.0)
        stype = s.get("type", "")
        if stype and stype.lower() in name.lower():
            title = f"🧵 {name} ({grams}g)"
        elif stype:
            title = f"🧵 {name} ({stype}, {grams}g)"
        else:
            title = f"🧵 {name} ({grams}g)"
        keyboard.append([KeyboardButton(text=title)])
    keyboard.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_ams_slots_keyboard(printer: BambuPrinter) -> ReplyKeyboardMarkup:
    active_key = printer.get_active_slot_key()
    mark = lambda key, label: f"{label} [⚡ АКТИВНИЙ]" if active_key == key else label

    if getattr(printer, "has_ams", False):
        keyboard = [
            [
                KeyboardButton(text=mark("0", "📍 Слот A1 (Slot 1)")),
                KeyboardButton(text=mark("1", "📍 Слот A2 (Slot 2)")),
            ],
            [
                KeyboardButton(text=mark("2", "📍 Слот A3 (Slot 3)")),
                KeyboardButton(text=mark("3", "📍 Слот A4 (Slot 4)")),
            ],
            [KeyboardButton(text=mark("255", "📍 Зовнішній слот (VT)"))],
            [KeyboardButton(text="⬅️ Назад")],
        ]
    else:
        keyboard = [
            [KeyboardButton(text=mark("255", "📍 Зовнішній котушкотримач (VT)"))],
            [KeyboardButton(text="⬅️ Назад")],
        ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_notify_keyboard(u_notify: dict) -> ReplyKeyboardMarkup:
    btn_start = "✅ Початок друку: Вкл" if u_notify.get("start", True) else "❌ Початок друку: Викл"
    btn_finish = "✅ Закінчення друку: Вкл" if u_notify.get("finish", True) else "❌ Закінчення друку: Викл"
    btn_pause = "✅ Пауза: Вкл" if u_notify.get("pause", True) else "❌ Пауза: Викл"
    btn_hms = "✅ HMS Помилки: Вкл" if u_notify.get("hms", True) else "❌ HMS Помилки: Викл"
    btn_clear = (
        "✅ Нагадування зняти деталь: Вкл"
        if u_notify.get("remind_clear", True)
        else "❌ Нагадування зняти деталь: Викл"
    )

    t_val = u_notify.get("min_time_to_end", 0)
    btn_time = f"⏳ Повідомити за {t_val} хв до кінця" if t_val > 0 else "⏳ Сповіщення за N хв (Вимк)"

    f_val = u_notify.get("min_filament", 0)
    btn_fil = f"📦 Попередження нитки < {f_val}g" if f_val > 0 else "📦 Попередження нитки < Xg (Вимк)"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_start), KeyboardButton(text=btn_finish)],
            [KeyboardButton(text=btn_pause), KeyboardButton(text=btn_hms)],
            [KeyboardButton(text=btn_time), KeyboardButton(text=btn_fil)],
            [KeyboardButton(text=btn_clear)],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
