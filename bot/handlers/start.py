"""
Start and access request handlers.
"""
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

from bot.keyboards import get_main_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)

    if message.from_user:
        user["personal"]["first_name"] = message.from_user.first_name or ""
        user["personal"]["last_name"] = message.from_user.last_name or ""
        user["personal"]["username"] = message.from_user.username or ""
    await app.storage.save_user(user)

    if not await app.is_user_approved(chat_id):
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Додати в команду")]], resize_keyboard=True)
        await message.answer(
            "Х-хмпф! Для отримання доступу натисни кнопку нижче... Тільки не змушуй мене чекати, Бака! 😤",
            reply_markup=keyboard
        )
        return

    is_adm = await app.is_user_admin(chat_id)
    await message.answer(
        "🤖 *Головне меню 3D Ферми*\nХ-хмпф! Ну й чого ти прийшов? Обирай розділ, тільки не затримуй мене, Бака! 😤💅",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(is_adm)
    )

@router.message(F.text == "Додати в команду")
async def handle_request_access(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        await message.answer(
            "📌 Вашу заявку прийнято! Чекай підтвердження від адміна й не біси мене! 😤"
        )
