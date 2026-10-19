"""
Keyboard builders for admin workflows.
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

def get_admin_keyboard(lang: str = "uk") -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=t("btn_users", lang))],
        [KeyboardButton(text=t("btn_new_users", lang))],
        [KeyboardButton(text=t("btn_main_menu", lang))],
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
