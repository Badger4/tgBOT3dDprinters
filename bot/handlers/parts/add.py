"""
Add part wizard handlers.
"""

import html
import uuid
from typing import Any
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from bot.keyboards import get_part_action_reply_keyboard, construct_part_info_keyboard
from bot.states import PartCreatingStates, PartEditingStates
from utils.i18n import get_user_lang
from bot.handlers.parts.view import send_part_info

router = Router()


@router.message(PartEditingStates.in_parts_list, F.text.lower().in_(["добавити", "➕ добавити", "додати", "➕ додати", "➕ додати деталь", "add", "➕ add", "add part"]))
@router.message(F.text.lower().in_(["добавити", "➕ добавити", "додати", "➕ додати", "➕ додати деталь", "add", "➕ add", "add part"]))
async def handle_add_part_start(message: Message, state: FSMContext, app: Any) -> None:
    await state.set_state(PartCreatingStates.name)
    await message.answer("Введіть назву нової деталі:")
