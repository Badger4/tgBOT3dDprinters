"""
Start and access request handlers.
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import get_main_keyboard, get_webapp_inline_keyboard

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)

    if message.from_user:
        user.setdefault("personal", {})
        user["personal"]["first_name"] = message.from_user.first_name or ""
        user["personal"]["last_name"] = message.from_user.last_name or ""
        user["personal"]["username"] = message.from_user.username or ""
    await app.storage.save_user(user)

    if not await app.is_user_approved(chat_id):
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Додати в команду")]], resize_keyboard=True)
        await message.answer(
            "Х-хмпф! Для отримання доступу натисни кнопку нижче... Тільки не змушуй мене чекати, Бака! 😤",
            reply_markup=keyboard,
        )
        return

    is_adm = await app.is_user_admin(chat_id)
    await message.answer(
        "🤖 *Головне меню 3D Ферми*\nХ-хмпф! Обирай розділ або відкривай WebApp! 😤💅",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(is_adm),
    )
    await message.answer(
        "📱 **Інтерактивний WebApp Дашборд:**", parse_mode=ParseMode.MARKDOWN, reply_markup=get_webapp_inline_keyboard()
    )


import html

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_CHAT_ID, logger


@router.message(F.text == "Додати в команду")
async def handle_request_access(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        await message.answer("📌 Вашу заявку прийнято! Чекай підтвердження від адміна й не біси мене! 😤")
        if app.bot and ADMIN_CHAT_ID:
            user_name = message.from_user.first_name if message.from_user else "Новий користувач"
            username_str = (
                f" (@{message.from_user.username})" if message.from_user and message.from_user.username else ""
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Схвалити", callback_data=f"approve_user_{chat_id}"),
                        InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject_user_{chat_id}"),
                    ],
                    [InlineKeyboardButton(text="👑 Зробити адміном", callback_data=f"make_admin_{chat_id}")],
                ]
            )
            try:
                await app.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🆕 <b>Заявка на доступ до 3D Ферми!</b>\n👤 <b>Користувач:</b> {html.escape(user_name)}{username_str}\n🔢 <b>ID:</b> <code>{chat_id}</code>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            except Exception as e:
                logger.warning(f"Could not notify admin of access request: {e}")
