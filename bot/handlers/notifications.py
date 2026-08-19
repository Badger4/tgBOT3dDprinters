"""
Global user notification settings handlers.
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import get_notify_keyboard

router = Router()


@router.message(
    F.text.lower().in_(
        [
            "🔔 налаштування сповіщень",
            "налаштування сповіщень",
            "🔔 сповіщення",
            "сповіщення",
            "🔔 notification settings",
            "notification settings",
        ]
    )
)
async def handle_notifications_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_notify = user.get("notify", {})
    u_lang = user.get("language", "uk")
    kb = get_notify_keyboard(u_notify, lang=u_lang)
    msg_title = "<b>⚙️ Notification Settings:</b>" if u_lang == "en" else "<b>⚙️ Налаштування сповіщень:</b>"
    await message.answer(
        msg_title,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


@router.message(F.text.startswith("🌐 Мова / Language"))
async def toggle_language(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    cur_lang = user.get("language", "uk")
    new_lang = "en" if cur_lang == "uk" else "uk"
    user["language"] = new_lang
    await app.storage.save_user(user)

    kb = get_notify_keyboard(user.get("notify", {}), lang=new_lang)
    confirm_text = (
        "🇬🇧 Language changed to <b>English</b>!"
        if new_lang == "en"
        else "🇺🇦 Мову інтерфейсу змінено на <b>Українську</b>!"
    )
    await message.answer(confirm_text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.message(F.text.startswith("✅ Початок друку:") | F.text.startswith("❌ Початок друку:"))
async def toggle_start_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["notify"]["start"] = not user["notify"].get("start", True)
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    await message.answer(
        f"Початок друку: {'Увімкнено ✅' if user['notify']['start'] else 'Вимкнено ❌'}", reply_markup=kb
    )


@router.message(F.text.startswith("✅ Закінчення друку:") | F.text.startswith("❌ Закінчення друку:"))
async def toggle_finish_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["notify"]["finish"] = not user["notify"].get("finish", True)
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    await message.answer(
        f"Закінчення друку: {'Увімкнено ✅' if user['notify']['finish'] else 'Вимкнено ❌'}", reply_markup=kb
    )


@router.message(F.text.startswith("✅ Пауза:") | F.text.startswith("❌ Пауза:"))
async def toggle_pause_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["notify"]["pause"] = not user["notify"].get("pause", True)
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    await message.answer(f"Пауза: {'Увімкнено ✅' if user['notify']['pause'] else 'Вимкнено ❌'}", reply_markup=kb)


@router.message(F.text.startswith("✅ HMS Помилки:") | F.text.startswith("❌ HMS Помилки:"))
async def toggle_hms_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["notify"]["hms"] = not user["notify"].get("hms", True)
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    await message.answer(f"HMS Помилки: {'Увімкнено ✅' if user['notify']['hms'] else 'Вимкнено ❌'}", reply_markup=kb)


@router.message(F.text.startswith("✅ Нагадування зняти деталь:") | F.text.startswith("❌ Нагадування зняти деталь:"))
async def toggle_clear_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    user["notify"]["remind_clear"] = not user["notify"].get("remind_clear", True)
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    await message.answer(
        f"Нагадування зняти деталь: {'Увімкнено ✅' if user['notify']['remind_clear'] else 'Вимкнено ❌'}",
        reply_markup=kb,
    )


@router.message(F.text.startswith("⏳ Повідомити за") | (F.text == "⏳ Сповіщення за N хв (Вимк)"))
async def handle_time_notify_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    time_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏳ 5 хв до кінця"), KeyboardButton(text="⏳ 10 хв до кінця")],
            [KeyboardButton(text="⏳ 15 хв до кінця"), KeyboardButton(text="❌ Вимкнути таймер сповіщень")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "⏳ <b>Оберіть час для запевного сповіщення до кінця друку:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=time_kb,
    )


@router.message(
    F.text.in_(["⏳ 5 хв до кінця", "⏳ 10 хв до кінця", "⏳ 15 хв до кінця", "❌ Вимкнути таймер сповіщень"])
)
async def handle_set_time_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    t_val = 5 if "5" in message.text else (10 if "10" in message.text else (15 if "15" in message.text else 0))
    user["notify"]["min_time_to_end"] = t_val
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    msg_str = (
        f"Встановити сповіщення за {t_val} хв до кінця ✅" if t_val > 0 else "Попереднє сповіщення за часом вимкнено ❌"
    )
    await message.answer(msg_str, reply_markup=kb)


@router.message(F.text.startswith("📦 Попередження нитки <"))
async def handle_filament_notify_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    fil_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Менше 50g"), KeyboardButton(text="📦 Менше 100g")],
            [KeyboardButton(text="📦 Менше 200g"), KeyboardButton(text="❌ Вимкнути ліміт нитки")],
            [KeyboardButton(text="⬅️ Назад")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "📦 <b>Оберіть поріг залишку нитки для попередження:</b>", parse_mode=ParseMode.HTML, reply_markup=fil_kb
    )


@router.message(F.text.in_(["📦 Менше 50g", "📦 Менше 100g", "📦 Менше 200g", "❌ Вимкнути ліміт нитки"]))
async def handle_set_filament_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    f_val = 50 if "50" in message.text else (100 if "100" in message.text else (200 if "200" in message.text else 0))
    user["notify"]["min_filament"] = f_val
    await app.storage.save_user(user)
    kb = get_notify_keyboard(user["notify"])
    msg_str = (
        f"Попереджувати, коли нитки менше {f_val}g ✅" if f_val > 0 else "Попередження за лімітом нитки вимкнено ❌"
    )
    await message.answer(msg_str, reply_markup=kb)
