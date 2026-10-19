"""
Keyboard builders for parts workflows.
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

def get_parts_reply_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="🔍 Пошук" if not is_en else "🔍 Search"),
            KeyboardButton(text="➕ Добавити" if not is_en else "➕ Add"),
        ],
        [
            KeyboardButton(text="📊 Звіт деталей (PDF)" if not is_en else "📊 Parts Report (PDF)"),
            KeyboardButton(text=t("btn_main_menu", lang)),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_search_reply_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="❌ Закінчити пошук" if not is_en else "❌ Finish Search"),
            KeyboardButton(text="⬅️ До списку деталей" if not is_en else "⬅️ Back to Parts"),
        ],
        [
            KeyboardButton(text=t("btn_main_menu", lang)),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_parts_inline_keyboard(parts: dict[str, dict[str, Any]] | list, max_items: int = 50) -> InlineKeyboardMarkup:
    if isinstance(parts, list):
        parts = {p["id"]: p for p in parts if isinstance(p, dict) and "id" in p}
    buttons = []
    count = 0
    for p_id, p in parts.items():
        if count >= max_items:
            break
        name = p.get("name", "Деталь")
        qty = p.get("count", p.get("quantity", 0))
        buttons.append([InlineKeyboardButton(text=f"{name} x{qty}", callback_data=f"part_view_{p_id}")])
        count += 1
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def construct_part_info_keyboard(part: dict[str, Any], lang: str = "uk") -> InlineKeyboardMarkup:
    p_id = part.get("id", "")
    name = part.get("name", "")
    count = part.get("count", part.get("quantity", 0))

    buttons = [
        [InlineKeyboardButton(text="🚀 Кинути на друк 🖨️", callback_data=f"part_print_select_{p_id}")],
        [InlineKeyboardButton(text=f"✏️ Ім'я: {name}", callback_data="part_prop_name")],
        [InlineKeyboardButton(text="✏️ Фото", callback_data="part_prop_image")],
        [InlineKeyboardButton(text=f"✏️ Кількість: x{count}", callback_data="part_prop_count")],
        [InlineKeyboardButton(text="✏️ .3mf файл", callback_data="part_prop_three_mf")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_printer_select_inline_keyboard(
    part_id: str,
    printers: dict[str, Any],
    part: dict[str, Any] | None = None,
    lang: str = "uk",
    spools_map: dict | None = None,
) -> InlineKeyboardMarkup:
    from services.gcode_parser import check_compatibility, get_printer_active_filament
    if isinstance(part, str):
        lang = part
        part = None
    buttons = []
    printer_model = part.get("printer_model", "") if isinstance(part, dict) else ""
    filament_type = part.get("filament_type", "") if isinstance(part, dict) else ""
    nozzle_diameter = part.get("nozzle_diameter", "") if isinstance(part, dict) else ""

    for p_id, p in printers.items():
        mapped = getattr(p, "mapped_state", "ONLINE")
        st_labels = {
            "ONLINE": "Онлайн" if lang != "en" else "Online",
            "OFFLINE": "Офлайн" if lang != "en" else "Offline",
            "RUNNING": "Друкує" if lang != "en" else "Printing",
            "PAUSE": "Пауза" if lang != "en" else "Pause",
        }
        state_str = f" ({st_labels.get(mapped, mapped)})"
        active_fil = get_printer_active_filament(p, spools_map)
        comp = check_compatibility(printer_model, filament_type, p.name, active_fil, printer=p, nozzle_diameter=nozzle_diameter) if printer_model else {"compatible": True}
        icon = "✅" if comp.get("compatible", True) else ("🛑" if comp.get("reason_type") in ["FILAMENT", "NOZZLE"] else "⚠️")
        cb = f"pxp:{part_id}:{p_id}"
        if len(cb.encode("utf-8")) > 64:
            cb = f"pxp:{part_id[:20]}:{p_id[:20]}"
        buttons.append([InlineKeyboardButton(text=f"{icon} 🖨️ {p.name}{state_str}", callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="⬅️ Скасувати" if lang != "en" else "⬅️ Cancel", callback_data=f"part_view_{part_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_part_action_reply_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="🚀 Кинути на друк" if not is_en else "🚀 Send to Print"),
            KeyboardButton(text="✏️ Редагувати" if not is_en else "✏️ Edit"),
        ],
        [
            KeyboardButton(text="🗑️ Видалити" if not is_en else "🗑️ Delete"),
            KeyboardButton(text="⬅️ До списку деталей" if not is_en else "⬅️ Back to Parts"),
        ],
        [
            KeyboardButton(text=t("btn_main_menu", lang)),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_part_editing_reply_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="💾 Зберегти" if not is_en else "💾 Save"),
            KeyboardButton(text="❌ Скасувати редагування" if not is_en else "❌ Cancel Edit"),
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_part_creation_reply_keyboard(lang: str = "uk", allow_skip: bool = False) -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = []
    if allow_skip:
        keyboard.append([KeyboardButton(text="⏩ Пропустити" if not is_en else "⏩ Skip")])
    keyboard.append([KeyboardButton(text="❌ Скасувати" if not is_en else "❌ Cancel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_part_cancel_inline_keyboard(lang: str = "uk", allow_skip: bool = False) -> InlineKeyboardMarkup:
    is_en = lang == "en"
    row = []
    if allow_skip:
        row.append(InlineKeyboardButton(text="⏩ Пропустити" if not is_en else "⏩ Skip", callback_data="skip_part_step"))
    row.append(InlineKeyboardButton(text="❌ Скасувати" if not is_en else "❌ Cancel", callback_data="cancel_part_creation"))
    return InlineKeyboardMarkup(inline_keyboard=[row])
