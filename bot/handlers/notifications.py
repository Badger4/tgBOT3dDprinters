"""
Global user notification settings handlers.
"""

from typing import Any

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


@router.message(F.text.startswith("🌐 Мова / Language") | F.text.startswith("🌐 Language / Мова"))
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


async def _sync_notify_change(app: Any, user: dict, key: str, value: Any):
    if "notify" not in user or not isinstance(user["notify"], dict):
        user["notify"] = {}
    user["notify"][key] = value
    await app.storage.save_user(user)

    if hasattr(app, "printers") and app.printers:
        for p in app.printers.values():
            if hasattr(p, "get_notify_dict"):
                if not isinstance(p.notify, dict):
                    p.notify = p.get_notify_dict()
                p.notify[key] = value
        if hasattr(app, "save_printers_config"):
            await app.save_printers_config()


@router.message(
    F.text.startswith("✅ Початок друку:")
    | F.text.startswith("❌ Початок друку:")
    | F.text.startswith("✅ Print Start:")
    | F.text.startswith("❌ Print Start:")
)
async def toggle_start_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    cur = user.get("notify", {}).get("start", True)
    new_val = not cur
    await _sync_notify_change(app, user, "start", new_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    await message.answer(
        f"Початок друку: {'Увімкнено ✅' if new_val else 'Вимкнено ❌'}" if u_lang != "en" else f"Print Start: {'On ✅' if new_val else 'Off ❌'}", reply_markup=kb
    )


@router.message(
    F.text.startswith("✅ Закінчення друку:")
    | F.text.startswith("❌ Закінчення друку:")
    | F.text.startswith("✅ Print Finish:")
    | F.text.startswith("❌ Print Finish:")
)
async def toggle_finish_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    cur = user.get("notify", {}).get("finish", True)
    new_val = not cur
    await _sync_notify_change(app, user, "finish", new_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    await message.answer(
        f"Закінчення друку: {'Увімкнено ✅' if new_val else 'Вимкнено ❌'}" if u_lang != "en" else f"Print Finish: {'On ✅' if new_val else 'Off ❌'}", reply_markup=kb
    )


@router.message(
    F.text.startswith("✅ Пауза:")
    | F.text.startswith("❌ Пауза:")
    | F.text.startswith("✅ Pause:")
    | F.text.startswith("❌ Pause:")
)
async def toggle_pause_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    cur = user.get("notify", {}).get("pause", True)
    new_val = not cur
    await _sync_notify_change(app, user, "pause", new_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    await message.answer(
        f"Пауза: {'Увімкнено ✅' if new_val else 'Вимкнено ❌'}" if u_lang != "en" else f"Pause: {'On ✅' if new_val else 'Off ❌'}", reply_markup=kb
    )


@router.message(
    F.text.startswith("✅ HMS Помилки:")
    | F.text.startswith("❌ HMS Помилки:")
    | F.text.startswith("✅ HMS Errors:")
    | F.text.startswith("❌ HMS Errors:")
)
async def toggle_hms_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    cur = user.get("notify", {}).get("hms", True)
    new_val = not cur
    await _sync_notify_change(app, user, "hms", new_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    await message.answer(
        f"HMS Помилки: {'Увімкнено ✅' if new_val else 'Вимкнено ❌'}" if u_lang != "en" else f"HMS Errors: {'On ✅' if new_val else 'Off ❌'}", reply_markup=kb
    )


@router.message(
    F.text.startswith("✅ Нагадування зняти деталь:")
    | F.text.startswith("❌ Нагадування зняти деталь:")
    | F.text.startswith("✅ Clear Bed Alert:")
    | F.text.startswith("❌ Clear Bed Alert:")
)
async def toggle_clear_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    cur = user.get("notify", {}).get("remind_clear", True)
    new_val = not cur
    await _sync_notify_change(app, user, "remind_clear", new_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    await message.answer(
        f"Нагадування зняти деталь: {'Увімкнено ✅' if new_val else 'Вимкнено ❌'}" if u_lang != "en" else f"Clear Bed Alert: {'On ✅' if new_val else 'Off ❌'}",
        reply_markup=kb,
    )


@router.message(F.text.startswith("⏳ Повідомити за") | (F.text == "⏳ Сповіщення за N хв (Вимк)") | F.text.startswith("⏳ ") & F.text.endswith("min before finish"))
async def handle_time_notify_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    time_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏳ 5 хв до кінця" if u_lang != "en" else "⏳ 5 min before finish"), KeyboardButton(text="⏳ 10 хв до кінця" if u_lang != "en" else "⏳ 10 min before finish")],
            [KeyboardButton(text="⏳ 15 хв до кінця" if u_lang != "en" else "⏳ 15 min before finish"), KeyboardButton(text="❌ Вимкнути таймер сповіщень" if u_lang != "en" else "❌ Disable timer")],
            [KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "⏳ <b>Оберіть час для запевного сповіщення до кінця друку:</b>" if u_lang != "en" else "⏳ <b>Select advance notification time before finish:</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=time_kb,
    )


@router.message(
    F.text.in_(
        [
            "⏳ 5 хв до кінця", "⏳ 10 хв до кінця", "⏳ 15 хв до кінця", "❌ Вимкнути таймер сповіщень",
            "⏳ 5 min before finish", "⏳ 10 min before finish", "⏳ 15 min before finish", "❌ Disable timer"
        ]
    )
)
async def handle_set_time_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    t_val = 5 if "5" in message.text else (10 if "10" in message.text else (15 if "15" in message.text else 0))
    await _sync_notify_change(app, user, "min_time_to_end", t_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    msg_str = (
        f"Встановити сповіщення за {t_val} хв до кінця ✅" if t_val > 0 else "Попереднє сповіщення за часом вимкнено ❌"
    ) if u_lang != "en" else (
        f"Set notification {t_val} min before finish ✅" if t_val > 0 else "Timer notification disabled ❌"
    )
    await message.answer(msg_str, reply_markup=kb)


@router.message(F.text.startswith("📦 Попередження нитки <") | F.text.startswith("📦 Filament <"))
async def handle_filament_notify_menu(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_approved(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    fil_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Менше 50g" if u_lang != "en" else "📦 Less than 50g"), KeyboardButton(text="📦 Менше 100g" if u_lang != "en" else "📦 Less than 100g")],
            [KeyboardButton(text="📦 Менше 200g" if u_lang != "en" else "📦 Less than 200g"), KeyboardButton(text="❌ Вимкнути ліміт нитки" if u_lang != "en" else "❌ Disable limit")],
            [KeyboardButton(text="⬅️ Назад" if u_lang != "en" else "⬅️ Back")],
        ],
        resize_keyboard=True,
    )
    await message.answer(
        "📦 <b>Оберіть поріг залишку нитки для попередження:</b>" if u_lang != "en" else "📦 <b>Select filament threshold for alert:</b>", parse_mode=ParseMode.HTML, reply_markup=fil_kb
    )


@router.message(
    F.text.in_(
        [
            "📦 Менше 50g", "📦 Менше 100g", "📦 Менше 200g", "❌ Вимкнути ліміт нитки",
            "📦 Less than 50g", "📦 Less than 100g", "📦 Less than 200g", "❌ Disable limit"
        ]
    )
)
async def handle_set_filament_notify(message: Message, app):
    chat_id = str(message.chat.id)
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    f_val = 50 if "50" in message.text else (100 if "100" in message.text else (200 if "200" in message.text else 0))
    await _sync_notify_change(app, user, "min_filament", f_val)
    kb = get_notify_keyboard(user["notify"], lang=u_lang)
    msg_str = (
        f"Попереджувати, коли нитки менше {f_val}g ✅" if f_val > 0 else "Попередження за лімітом нитки вимкнено ❌"
    ) if u_lang != "en" else (
        f"Alert when filament is less than {f_val}g ✅" if f_val > 0 else "Filament limit alert disabled ❌"
    )
    await message.answer(msg_str, reply_markup=kb)
