"""
Keyboard builders for common workflows.
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

def get_main_keyboard(is_admin: bool, lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = []
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        keyboard.append([KeyboardButton(text=t("btn_open_webapp", lang), web_app=WebAppInfo(url=WEBAPP_URL))])

    keyboard.extend(
        [
            [KeyboardButton(text=t("btn_farm_status", lang)), KeyboardButton(text=t("btn_printers", lang))],
            [KeyboardButton(text=t("btn_warehouse", lang)), KeyboardButton(text=t("btn_parts_warehouse", lang))],
            [KeyboardButton(text=t("btn_history", lang)), KeyboardButton(text=t("btn_commercial", lang))],
        ]
    )
    if is_admin:
        keyboard.append([KeyboardButton(text=t("btn_notify_settings", lang)), KeyboardButton(text=t("btn_admin", lang))])
    else:
        keyboard.append([KeyboardButton(text=t("btn_notify_settings", lang))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_webapp_inline_keyboard() -> InlineKeyboardMarkup:
    if WEBAPP_URL and WEBAPP_URL.startswith("https://"):
        btn = InlineKeyboardButton(text="📱 Відкрити WebApp 🚀", web_app=WebAppInfo(url=WEBAPP_URL))
    else:
        btn = InlineKeyboardButton(
            text="🌐 Відкрити WebApp в браузері 🚀", url=WEBAPP_URL or "http://localhost:8080/webapp"
        )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


def get_wizard_nav_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    """Navigation keyboard for wizard steps: step back or cancel."""
    btn_step_back = "↩️ Крок назад" if lang != "en" else "↩️ Step back"
    btn_cancel = "❌ Скасувати" if lang != "en" else "❌ Cancel"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn_step_back), KeyboardButton(text=btn_cancel)]],
        resize_keyboard=True,
    )


def get_live_status_inline_keyboard(lang: str = "uk") -> InlineKeyboardMarkup:
    """Inline keyboard for live farm dashboard message with in-place refresh."""
    is_en = lang == "en"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Оновити статус" if not is_en else "🔄 Refresh Status",
                    callback_data="refresh_live_status",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💡 Світло: Все Увімк" if not is_en else "💡 Lights: All On",
                    callback_data="batch_light_on",
                ),
                InlineKeyboardButton(
                    text="🌑 Світло: Все Вимк" if not is_en else "🌑 Lights: All Off",
                    callback_data="batch_light_off",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Калібрувати вільні" if not is_en else "🎯 Calibrate Idle",
                    callback_data="batch_calibrate_prompt",
                )
            ]
        ]
    )
