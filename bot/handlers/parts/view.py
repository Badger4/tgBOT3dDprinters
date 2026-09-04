"""
Parts warehouse view handlers.
"""

import html
from pathlib import Path
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, FSInputFile
from config import logger
from bot.keyboards import (
    construct_part_info_keyboard,
    get_part_action_reply_keyboard,
    get_parts_inline_keyboard,
    get_parts_reply_keyboard,
)
from bot.states import PartEditingStates
from functions.i18n import get_user_lang

router = Router()


async def open_parts_list(message: Message, state: FSMContext, app: Any, lang: str = "uk") -> None:
    await state.set_state(PartEditingStates.in_parts_list)
    parts: dict[str, dict[str, Any]] = await app.storage.load_parts()

    text_keyboard = get_parts_reply_keyboard(lang)
    inline_keyboard = get_parts_inline_keyboard(parts)

    await message.answer(".", reply_markup=text_keyboard)
    if not parts:
        await message.answer(
            "🧩 <b>Склад деталей порожній!</b>\nНатисніть <b>Добавити</b>, щоб додати першу деталь.",
            parse_mode=ParseMode.HTML,
            reply_markup=inline_keyboard,
        )
    else:
        await message.answer("Список деталей:", reply_markup=inline_keyboard)


@router.message(F.text.in_(["🧩 Склад деталей", "🧩 Parts Stock", "Склад деталей", "3Д"]))
async def handle_parts_warehouse_btn(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    u_data = await app.storage.load_user(message.from_user.id)
    lang = get_user_lang(u_data)
    await open_parts_list(message, state, app, lang)


async def send_part_info(target_message: Message, part: dict[str, Any], text_keyboard: ReplyKeyboardMarkup, inline_keyboard: InlineKeyboardMarkup) -> None:
    await target_message.answer(".", reply_markup=text_keyboard)

    img = str(part.get("image", "") or "").strip()
    name = html.escape(part.get("name", "Деталь"))
    p_model = part.get("printer_model")
    model_para = f"\n🖨️ <b>Принтер:</b> {html.escape(p_model)}" if p_model and p_model != "Unknown" else ""
    cnt = part.get("count", part.get("quantity", 0))
    caption_text = f"🧩 <b>{name}</b>{model_para}\n📦 <b>Кількість:</b> {cnt} шт"

    photo_sent = False
    if img:
        try:
            if img.startswith("http://") or img.startswith("https://") or (len(img) > 15 and "/" not in img and "\\" not in img):
                await target_message.answer_photo(photo=img, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                photo_sent = True
            else:
                import config
                img_file_name = Path(img).name
                p = config.STORAGE_DIR / "uploads" / img_file_name
                if not p.exists():
                    p = Path(img)
                if not p.exists():
                    p = config.STORAGE_DIR / img
                if p.exists():
                    await target_message.answer_photo(photo=FSInputFile(p), caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
                    photo_sent = True
        except Exception as e:
            logger.warning(f"Error sending photo [{img}]: {e}")

    if not photo_sent:
        await target_message.answer(caption_text, parse_mode=ParseMode.HTML, reply_markup=inline_keyboard)
