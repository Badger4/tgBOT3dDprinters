"""
Reply and Inline keyboard builders for Telegram Bot.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL
from models.printer import BambuPrinter
from utils.i18n import t


def get_main_keyboard(is_admin: bool, lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = []
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        keyboard.append([KeyboardButton(text=t("btn_open_webapp", lang), web_app=WebAppInfo(url=WEBAPP_URL))])

    keyboard.extend(
        [
            [KeyboardButton(text=t("btn_printers", lang)), KeyboardButton(text=t("btn_farm_status", lang))],
            [KeyboardButton(text=t("btn_warehouse", lang)), KeyboardButton(text=t("btn_parts_warehouse", lang))],
            [KeyboardButton(text=t("btn_history", lang)), KeyboardButton(text=t("btn_commercial", lang))],
            [KeyboardButton(text=t("btn_notify_settings", lang))],
        ]
    )
    if is_admin:
        keyboard.append([KeyboardButton(text=t("btn_admin", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_webapp_inline_keyboard() -> InlineKeyboardMarkup:
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        btn = InlineKeyboardButton(text="📱 Відкрити WebApp 🚀", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        btn = InlineKeyboardButton(
            text="🌐 Відкрити WebApp в браузері 🚀", url=WEBAPP_URL or "http://localhost:8080/webapp"
        )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def get_printers_keyboard(printers: dict[str, Any], lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = []
    for p in printers.values():
        p_name = p.name if hasattr(p, "name") else (p.get("name", "Printer") if isinstance(p, dict) else "Printer")
        keyboard.append([KeyboardButton(text=f"🖨️ {p_name}")])
    keyboard.append([KeyboardButton(text=t("btn_add_printer", lang))])
    keyboard.append([KeyboardButton(text=t("btn_main_menu", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_printers_mount_keyboard(printers: dict[str, Any], lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = []
    for p in printers.values():
        p_name = p.name if hasattr(p, "name") else (p.get("name", "Printer") if isinstance(p, dict) else "Printer")
        keyboard.append([KeyboardButton(text=f"🖨️ {p_name}")])
    keyboard.append([KeyboardButton(text=t("btn_back", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)



def get_printer_menu_keyboard(printer: BambuPrinter, lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=t("btn_status", lang)), KeyboardButton(text=t("btn_camera", lang))],
        [KeyboardButton(text=t("btn_control", lang)), KeyboardButton(text=t("btn_filament", lang))],
        [KeyboardButton(text=t("btn_edit_printer", lang)), KeyboardButton(text=t("btn_delete_printer", lang))],
        [KeyboardButton(text=t("btn_back_to_printers", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_edit_printer_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    is_en = lang == "en"
    notify_str = "🔔 Сповіщення" if not is_en else "🔔 Notifications"
    nozzle_str = "🎯 Діаметр сопла" if not is_en else "🎯 Nozzle Diameter"
    keyboard = [
        [KeyboardButton(text=t("btn_edit_p_name", lang)), KeyboardButton(text=t("btn_edit_p_ip", lang))],
        [KeyboardButton(text=t("btn_edit_p_sn", lang)), KeyboardButton(text=t("btn_edit_p_code", lang))],
        [KeyboardButton(text=nozzle_str), KeyboardButton(text=notify_str)],
        [KeyboardButton(text=t("btn_back", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_nozzle_diameters_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🎯 0.2 мм"), KeyboardButton(text="🎯 0.4 мм")],
        [KeyboardButton(text="🎯 0.6 мм"), KeyboardButton(text="🎯 0.8 мм")],
        [KeyboardButton(text=t("btn_back", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_printer_models_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="🖨️ A1 mini"), KeyboardButton(text="🖨️ A1"), KeyboardButton(text="🖨️ A2L")],
        [KeyboardButton(text="🖨️ P1P"), KeyboardButton(text="🖨️ P1S"), KeyboardButton(text="🖨️ P2S")],
        [KeyboardButton(text="🖨️ X1"), KeyboardButton(text="🖨️ X1 Carbon (X1C)"), KeyboardButton(text="🖨️ X1E")],
        [KeyboardButton(text="🖨️ X2D"), KeyboardButton(text="🖨️ H2S"), KeyboardButton(text="🖨️ H2D")],
        [KeyboardButton(text="🖨️ H2D Pro"), KeyboardButton(text="🖨️ H2C")],
        [KeyboardButton(text=t("btn_back", lang))],
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


def get_printer_control_keyboard(printer: BambuPrinter, lang: str = "uk") -> ReplyKeyboardMarkup:
    raw_st = str(getattr(printer, "gcode_state", "IDLE")).upper()
    mapped_st = str(getattr(printer, "mapped_state", "IDLE")).upper()

    is_printing = (mapped_st in ["RUNNING", "PAUSE"]) and (raw_st not in ["FINISH", "IDLE", "SUCCESS", "FAILED", "CANCEL", "OFFLINE"])
    keyboard = []

    if is_printing:
        if raw_st in ["PAUSE", "PAUSED"] or mapped_st == "PAUSE":
            pause_resume_btn = KeyboardButton(text=t("btn_resume_print", lang))
        else:
            pause_resume_btn = KeyboardButton(text=t("btn_pause_print", lang))

        keyboard.append([KeyboardButton(text=t("btn_speed", lang)), KeyboardButton(text=t("btn_light", lang))])
        keyboard.append([KeyboardButton(text=t("btn_stop_print", lang)), pause_resume_btn])
    else:
        keyboard.append([KeyboardButton(text=t("btn_light", lang))])

    keyboard.append([KeyboardButton(text=t("btn_calibrate", lang)), KeyboardButton(text=t("btn_reset_maint", lang))])

    if is_printing:
        keyboard.append([KeyboardButton(text="🚫 Пропустити об'єкт")])

    is_en = lang == "en"
    load_btn_text = "⬇️ Load Filament" if is_en else "⬇️ Завантажити філамент"
    unload_btn_text = "⬆️ Unload Filament" if is_en else "⬆️ Зняти філамент"
    keyboard.append([KeyboardButton(text=load_btn_text), KeyboardButton(text=unload_btn_text)])

    keyboard.append([KeyboardButton(text=t("btn_back", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def build_skip_objects_keyboard(printer: BambuPrinter, lang: str = "uk") -> InlineKeyboardMarkup:
    """Builds interactive compact inline buttons to skip objects on the active print plate."""
    buttons = []
    current_row = []
    skipped = getattr(printer, "skipped_objects", [])
    objects = getattr(printer, "current_job_objects", [])

    for obj in objects:
        obj_id = obj.get("id")
        obj_id_int = int(obj_id) if str(obj_id).isdigit() else obj_id
        is_skipped = obj_id_int in skipped or str(obj_id_int) in [str(s) for s in skipped]

        if is_skipped:
            btn_text = f"❌ #{obj_id}"
            callback = f"skip_obj_done:{printer.id}:{obj_id}"
        else:
            btn_text = f"🚫 #{obj_id}"
            callback = f"skip_obj_act:{printer.id}:{obj_id}"

        current_row.append(InlineKeyboardButton(text=btn_text, callback_data=callback))
        if len(current_row) >= 3:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=t("btn_users", lang))],
        [KeyboardButton(text=t("btn_new_users", lang))],
        [KeyboardButton(text=t("btn_main_menu", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


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


def get_wizard_nav_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    """Navigation keyboard for wizard steps: step back or cancel."""
    btn_step_back = "↩️ Крок назад" if lang != "en" else "↩️ Step back"
    btn_cancel = "❌ Скасувати" if lang != "en" else "❌ Cancel"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn_step_back), KeyboardButton(text=btn_cancel)]],
        resize_keyboard=True,
    )


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

        if not vt_type:
            f_type = getattr(printer, "filament_type", "")
            if f_type and f_type not in ["Невизначено", "None", "", "Порожньо", "Empty"]:
                vt_type = f_type

        if vt_empty and not vt_type and vt_grams <= 0 and not vt_is_act:
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



def get_parts_inline_keyboard(parts: dict[str, dict[str, Any]] | list) -> InlineKeyboardMarkup:
    if isinstance(parts, list):
        parts = {p["id"]: p for p in parts if isinstance(p, dict) and "id" in p}
    buttons = []
    for p_id, p in parts.items():
        name = p.get("name", "Деталь")
        count = p.get("count", p.get("quantity", 0))
        buttons.append([InlineKeyboardButton(text=f"{name} x{count}", callback_data=f"part_view_{p_id}")])
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
        buttons.append([InlineKeyboardButton(text=f"{icon} 🖨️ {p.name}{state_str}", callback_data=f"part_exec_print:{part_id}:{p_id}")])
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





