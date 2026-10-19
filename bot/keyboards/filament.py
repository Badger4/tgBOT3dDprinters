"""
Keyboard builders for filament workflows.
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
from bot.keyboards.history import get_movements_spool_select_keyboard

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


def get_spool_presets_inline_keyboard(
    presets: dict[str, dict[str, Any]] | None = None, lang: str = "uk"
) -> InlineKeyboardMarkup:
    if presets:
        buttons = []
        row = []
        for pid, p in presets.items():
            name = p.get("name", pid)
            price = p.get("price_per_kg") or p.get("price_uah") or 850.0
            label = f"{name} ({price:.0f} грн)"
            row.append(InlineKeyboardButton(text=label, callback_data=f"spool_preset:{pid}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        if buttons:
            return InlineKeyboardMarkup(inline_keyboard=buttons)

    buttons = [
        [
            InlineKeyboardButton(text="⚫ Bambu PLA Black (850 грн)", callback_data="spool_preset:bambu_pla_black"),
            InlineKeyboardButton(text="⚪ Sunlu PLA White (650 грн)", callback_data="spool_preset:sunlu_pla_white"),
        ],
        [
            InlineKeyboardButton(text="🩶 eSUN PETG Grey (700 грн)", callback_data="spool_preset:esun_petg_grey"),
            InlineKeyboardButton(text="🔴 TPU 95A Red (950 грн)", callback_data="spool_preset:tpu_red"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_spool_price_keyboard(grams: float = 1000.0, lang: str = "uk") -> ReplyKeyboardMarkup:
    """Navigation keyboard for spool price step with total price option."""
    kg = (grams or 1000.0) / 1000.0
    kg_str = f"{kg:g}"
    if lang != "en":
        btn_total = f"🏷️ Ціна за всю котушку ({kg_str} кг)" if kg != 1 else "🏷️ Ціна за всю котушку"
        btn_step_back = "↩️ Крок назад"
        btn_cancel = "❌ Скасувати"
    else:
        btn_total = f"🏷️ Price for entire spool ({kg_str} kg)" if kg != 1 else "🏷️ Price for entire spool"
        btn_step_back = "↩️ Step back"
        btn_cancel = "❌ Cancel"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_total)],
            [KeyboardButton(text=btn_step_back), KeyboardButton(text=btn_cancel)],
        ],
        resize_keyboard=True,
    )


def get_filament_types_keyboard(lang: str = "uk", include_step_back: bool = True) -> ReplyKeyboardMarkup:
    """Returns reply keyboard with popular filament types for quick 1-tap selection without auto-detection."""
    popular = [
        "PLA", "PETG", "ABS",
        "TPU", "ASA", "PC",
        "PLA-CF", "PETG-CF", "PA-CF",
        "PA", "PCTG", "HIPS",
        "PPA-CF", "PET-CF", "ABS-GF",
        "PVA", "PP", "BVOH",
    ]

    keyboard = []
    for i in range(0, len(popular), 3):
        chunk = popular[i : i + 3]
        keyboard.append([KeyboardButton(text=f) for f in chunk])

    if include_step_back:
        btn_step_back = "↩️ Крок назад" if lang != "en" else "↩️ Step back"
        btn_cancel = "❌ Скасувати" if lang != "en" else "❌ Cancel"
        keyboard.append([KeyboardButton(text=btn_step_back), KeyboardButton(text=btn_cancel)])
    else:
        keyboard.append([KeyboardButton(text=t("btn_back", lang))])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_filament_colors_keyboard(lang: str = "uk", include_step_back: bool = True) -> ReplyKeyboardMarkup:
    """Returns compact keyboard with popular base filament colors."""
    if lang != "en":
        keyboard = [
            [KeyboardButton(text="⚫ Чорний"), KeyboardButton(text="⚪ Білий"), KeyboardButton(text="🩶 Сірий"), KeyboardButton(text="🔘 Прозорий")],
            [KeyboardButton(text="🔴 Червоний"), KeyboardButton(text="🔵 Синій"), KeyboardButton(text="🟢 Зелений"), KeyboardButton(text="🟡 Жовтий")],
        ]
        btn_step_back = "↩️ Крок назад"
        btn_cancel = "❌ Скасувати"
    else:
        keyboard = [
            [KeyboardButton(text="⚫ Black"), KeyboardButton(text="⚪ White"), KeyboardButton(text="🩶 Grey"), KeyboardButton(text="🔘 Clear")],
            [KeyboardButton(text="🔴 Red"), KeyboardButton(text="🔵 Blue"), KeyboardButton(text="🟢 Green"), KeyboardButton(text="🟡 Yellow")],
        ]
        btn_step_back = "↩️ Step back"
        btn_cancel = "❌ Cancel"

    if include_step_back:
        keyboard.append([KeyboardButton(text=btn_step_back), KeyboardButton(text=btn_cancel)])
    else:
        keyboard.append([KeyboardButton(text=t("btn_back", lang))])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spool_quantity_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    """Returns keyboard with quick quantity presets and navigation."""
    is_en = lang == "en"
    suffix = " pcs" if is_en else " шт"
    keyboard = [
        [KeyboardButton(text=f"1{suffix}"), KeyboardButton(text=f"2{suffix}"), KeyboardButton(text=f"3{suffix}"), KeyboardButton(text=f"4{suffix}")],
        [KeyboardButton(text=f"5{suffix}"), KeyboardButton(text=f"7{suffix}"), KeyboardButton(text=f"10{suffix}"), KeyboardButton(text=f"20{suffix}")],
        [
            KeyboardButton(text="↩️ Крок назад" if not is_en else "↩️ Step back"),
            KeyboardButton(text="❌ Скасувати" if not is_en else "❌ Cancel"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_filament_menu_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=t("btn_add_spool", lang)), KeyboardButton(text=t("btn_rfid_sync", lang))],
        [KeyboardButton(text=t("btn_mount_spool", lang)), KeyboardButton(text=t("btn_unmount_spool", lang))],
        [KeyboardButton(text=t("btn_edit_spool", lang)), KeyboardButton(text=t("btn_delete_spool", lang))],
        [KeyboardButton(text=t("btn_spool_movements", lang)), KeyboardButton(text=t("btn_spools_pdf", lang))],
        [KeyboardButton(text=t("btn_back", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_single_printer_filament_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="🔗 Поставити котушку" if not is_en else "🔗 Mount Spool"),
            KeyboardButton(text="🔓 Зняти котушку" if not is_en else "🔓 Unmount Spool"),
        ],
        [
            KeyboardButton(text="✏️ Змінити вагу" if not is_en else "✏️ Edit Weight"),
            KeyboardButton(text=t("btn_spool_movements", lang)),
        ],
        [
            KeyboardButton(text="⬅️ Назад" if not is_en else "⬅️ Back"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spools_keyboard(spools: dict[str, dict[str, Any]], lang: str = "uk") -> ReplyKeyboardMarkup:
    from utils.filament_utils import get_color_emoji

    keyboard = []
    for s_id, s in spools.items():
        name = s.get("name", "Spool")
        grams = s.get("remaining_grams", 1000.0)
        stype = s.get("type", "")
        qty = max(1, int(s.get("quantity", 1) or 1))
        color_emoji = get_color_emoji(s.get("color_name") or s.get("color", ""))
        c_prefix = f"{color_emoji} " if color_emoji else ""
        type_str = f"{stype}, " if (stype and stype.lower() not in name.lower()) else ""
        qty_unit = "pcs" if lang == "en" else "шт"
        qty_str = f" [📦 {qty} {qty_unit}]" if qty > 1 else ""
        title = f"🧵 {c_prefix}{name} ({type_str}{grams}g){qty_str}"
        keyboard.append([KeyboardButton(text=title)])
    keyboard.append([KeyboardButton(text=t("btn_back", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_ams_slots_keyboard(printer: BambuPrinter, lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    from utils.filament_utils import get_color_emoji

    active_k = printer.get_active_slot_key() if hasattr(printer, "get_active_slot_key") else "254"
    if callable(active_k):
        try:
            active_k = active_k()
        except Exception:
            active_k = "254"
    active_key = str(active_k) if active_k is not None else "254"

    trays = getattr(printer, "ams_trays_info", {}) or {}
    if not isinstance(trays, dict):
        trays = {}

    def _safe_float(val: Any, default: float = 0.0) -> float:
        if callable(val):
            try:
                val = val()
            except Exception:
                return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def build_slot_btn(idx: int) -> KeyboardButton:
        slot_k = str(idx)
        slot_name = f"A{idx + 1}"
        t_info = trays.get(slot_k, {})
        is_empty = t_info.get("empty", True) if t_info else True
        t_type = str(t_info.get("type") or t_info.get("tray_type") or "").strip()
        t_color = str(t_info.get("color") or t_info.get("tray_color") or "")
        rem_pct = t_info.get("remain", -1)
        raw_slot_g = printer.get_slot_grams(slot_k) if hasattr(printer, "get_slot_grams") else 0.0
        slot_g = _safe_float(raw_slot_g)

        is_act = (slot_k == active_key)
        act_icon = " ⚡" if is_act else ""

        if is_empty or (not t_type and slot_g <= 0):
            empty_lbl = "Empty" if is_en else "Порожньо"
            return KeyboardButton(text=f"⚪ {slot_name}: {empty_lbl}{act_icon}")

        c_emoji = get_color_emoji(t_color)
        mat_type = t_type if t_type else ("Filament" if is_en else "Філамент")

        rem_part = ""
        if rem_pct >= 0:
            rem_part = f" {rem_pct}%"
        elif slot_g > 0:
            rem_part = f" {slot_g:.0f}g"

        return KeyboardButton(text=f"{c_emoji} {slot_name}: {mat_type}{rem_part}{act_icon}")

    def build_vt_btn() -> KeyboardButton:
        vt_info = trays.get("254", {})
        vt_empty = vt_info.get("empty", True) if vt_info else True
        vt_type = str(vt_info.get("type") or vt_info.get("tray_type") or "").strip()
        vt_color = str(vt_info.get("color") or vt_info.get("tray_color") or "")
        vt_rem = vt_info.get("remain", -1)
        raw_vt_g = printer.get_slot_grams("254") if hasattr(printer, "get_slot_grams") else 0.0
        vt_grams = _safe_float(raw_vt_g)
        vt_is_act = (active_key in ["254", "255"])
        vt_act = " ⚡" if vt_is_act else ""

        if not vt_type and vt_is_act:
            f_type = getattr(printer, "filament_type", "")
            if f_type and f_type not in ["Невизначено", "None", "", "Порожньо", "Empty"]:
                vt_type = f_type

        if (vt_empty or not vt_type) and vt_grams <= 0 and not vt_is_act:
            empty_lbl = "Empty" if is_en else "Порожньо"
            return KeyboardButton(text=f"⚪ VT: {empty_lbl}")

        c_emoji = get_color_emoji(vt_color) if vt_color else "🧵"
        mat_type = vt_type if vt_type else ("External" if is_en else "Зовнішній")

        rem_part = ""
        if vt_rem >= 0:
            rem_part = f" {vt_rem}%"
        elif vt_grams > 0:
            rem_part = f" {vt_grams:.0f}g"

        return KeyboardButton(text=f"{c_emoji} VT: {mat_type}{rem_part}{vt_act}")

    p_has_ams = bool(getattr(printer, "has_ams", False))

    if p_has_ams:
        keyboard = [
            [build_slot_btn(0), build_slot_btn(1)],
            [build_slot_btn(2), build_slot_btn(3)],
            [build_vt_btn()],
            [KeyboardButton(text=t("btn_back", lang))],
        ]
    else:
        keyboard = [
            [build_vt_btn()],
            [KeyboardButton(text=t("btn_back", lang))],
        ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spool_edit_fields_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="🏷️ Name" if is_en else "🏷️ Назва"),
            KeyboardButton(text="🎨 Type" if is_en else "🎨 Тип"),
        ],
        [
            KeyboardButton(text="🌈 Color" if is_en else "🌈 Колір"),
            KeyboardButton(text="📦 Quantity" if is_en else "📦 Кількість"),
        ],
        [
            KeyboardButton(text="⚖️ Remaining (g)" if is_en else "⚖️ Залишок (г)"),
            KeyboardButton(text="💰 Price per kg" if is_en else "💰 Вартість (грн)"),
        ],
        [KeyboardButton(text=t("btn_back", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_confirm_delete_spool_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    keyboard = [
        [
            KeyboardButton(text="🗑️ Yes, delete" if is_en else "🗑️ Так, видалити"),
            KeyboardButton(text="❌ Cancel" if is_en else "❌ Скасувати"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_spool_filter_keyboard(
    spools: dict[str, dict[str, Any]],
    current_filter: str = "all",
    lang: str = "uk",
) -> InlineKeyboardMarkup:
    """Legacy wrapper delegating to modern spool selector."""
    return get_movements_spool_select_keyboard(spools, current_spool=current_filter, page=0, lang=lang)


def get_warehouse_pdf_keyboard(lang: str = "uk") -> InlineKeyboardMarkup:
    is_en = lang == "en"
    buttons = [
        [InlineKeyboardButton(text="📦 " + ("Stock Inventory (PDF)" if is_en else "Залишки на складі (PDF)"), callback_data="pdf_export_spools")],
        [InlineKeyboardButton(text="📜 " + ("Movements Audit (PDF)" if is_en else "Журнал аудиту руху (PDF)"), callback_data="pdf_export_movements")],
        [InlineKeyboardButton(text="📥 " + ("Download Both Reports" if is_en else "Завантажити обидва звіти"), callback_data="pdf_export_both")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
