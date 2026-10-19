"""
Keyboard builders for printers workflows.
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


def get_farm_batch_actions_keyboard(lang: str = "uk") -> InlineKeyboardMarkup:
    """Inline keyboard for batch fleet actions on farm dashboard."""
    is_en = lang == "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💡 Увімкнути все світло" if not is_en else "💡 Turn All Lights On",
                    callback_data="batch_light_on",
                ),
                InlineKeyboardButton(
                    text="🌑 Вимкнути все світло" if not is_en else "🌑 Turn All Lights Off",
                    callback_data="batch_light_off",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Калібрувати всі вільні" if not is_en else "🎯 Calibrate All Idle",
                    callback_data="batch_calibrate_prompt",
                )
            ],
        ]
    )


def get_fleet_calibrate_confirm_keyboard(lang: str = "uk") -> InlineKeyboardMarkup:
    """Confirmation inline keyboard before starting batch calibration."""
    is_en = lang == "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити калібрування" if not is_en else "✅ Confirm Calibration",
                    callback_data="batch_calibrate_confirm",
                ),
                InlineKeyboardButton(
                    text="❌ Скасувати" if not is_en else "❌ Cancel",
                    callback_data="batch_calibrate_cancel",
                ),
            ]
        ]
    )
