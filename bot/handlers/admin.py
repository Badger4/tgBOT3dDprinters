"""
Admin panel and user management handlers.
"""
import re
import html
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

from config import logger, ADMIN_CHAT_ID
from bot.keyboards import get_admin_keyboard

router = Router()

@router.message(F.text.lower().in_(["👑 адмінка", "адмінка", "повернутись в адмінку"]))
async def handle_admin_panel(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    await message.answer("*👑 Панель Адміністратора*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

@router.message(F.text == "👥 Користувачі")
async def handle_list_approved_users(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    all_users = await app.storage.load_all_users()
    btn_list = []
    for uid, udata in all_users.items():
        if udata.get("is_approved") or await app.is_user_admin(uid):
            name = udata.get("personal", {}).get("first_name", "User")
            role = "👑" if await app.is_user_admin(uid) else "👤"
            btn_list.append([KeyboardButton(text=f"{role} {name} ({uid})")])
    btn_list.append([KeyboardButton(text="Повернутись в адмінку")])
    await message.answer("*Список затверджених користувачів:*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(keyboard=btn_list, resize_keyboard=True))

@router.message(F.text == "🆕 Нові користувачі")
async def handle_list_pending_users(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    all_users = await app.storage.load_all_users()
    btn_list = []
    for uid, udata in all_users.items():
        if not udata.get("is_approved") and not await app.is_user_admin(uid):
            name = udata.get("personal", {}).get("first_name", "Новий")
            btn_list.append([KeyboardButton(text=f"⏳ {name} ({uid})")])
    if not btn_list:
        await message.answer("*Немає нових користувачів.*", parse_mode=ParseMode.MARKDOWN)
        return
    btn_list.append([KeyboardButton(text="Повернутись в адмінку")])
    await message.answer("*Нові користувачі на підтвердженні:*", parse_mode=ParseMode.MARKDOWN, reply_markup=ReplyKeyboardMarkup(keyboard=btn_list, resize_keyboard=True))

@router.message(F.text.in_(["✅ Додати в команду", "❌ Видалити з команди", "👑 Призначити адміном", "🔻 Забрати адміна"]))
async def handle_manage_user_action(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    if user.get("state") != "manage_user":
        return

    ctx_data = user.get("context_data", {})
    target_uid = ctx_data.get("manage_user_id")
    if not target_uid:
        return

    target_u = await app.storage.load_user(target_uid)
    action_msg = ""
    text = message.text

    if text == "✅ Додати в команду":
        target_u["is_approved"] = True
        await app.storage.save_user(target_u)
        action_msg = f"✅ Користувача <code>{html.escape(str(target_uid))}</code> успішно додано в команду, Бака! 😤"
        try:
            if app.bot:
                await app.bot.send_message(
                    chat_id=target_uid,
                    text="🎉 <b>Вітаємо! Адміністратор надав вам доступ до 3D Ферми!</b>\nНатисніть /start для переходу до головного меню.",
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.warning(f"Failed sending approval notification to {target_uid}: {e}")

    elif text == "❌ Видалити з команди":
        target_u["is_approved"] = False
        await app.storage.save_user(target_u)
        action_msg = f"❌ Користувача <code>{html.escape(str(target_uid))}</code> видалено з команди!"

    elif text == "👑 Призначити адміном":
        if "admin" not in target_u:
            target_u["admin"] = {}
        target_u["admin"]["access_admin"] = True
        await app.storage.save_user(target_u)
        action_msg = f"👑 Користувача <code>{html.escape(str(target_uid))}</code> призначено адміністратором!"

    elif text == "🔻 Забрати адміна":
        if str(target_uid) == str(ADMIN_CHAT_ID):
            action_msg = "⚠️ Неможливо забрати адмін-права у головного адміністратора!"
        else:
            if "admin" not in target_u:
                target_u["admin"] = {}
            target_u["admin"]["access_admin"] = False
            await app.storage.save_user(target_u)
            action_msg = f"🔻 Адмін-права для <code>{html.escape(str(target_uid))}</code> скасовано."

    is_app = target_u.get("is_approved", False)
    is_t_adm = await app.is_user_admin(target_uid)
    btn_team = "❌ Видалити з команди" if is_app else "✅ Додати в команду"
    btn_admin = "🔻 Забрати адміна" if is_t_adm else "👑 Призначити адміном"

    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=btn_team)],
        [KeyboardButton(text=btn_admin)],
        [KeyboardButton(text="Повернутись в адмінку")]
    ], resize_keyboard=True)

    p = target_u.get("personal", {})
    first_name = html.escape(str(p.get("first_name", "")))
    last_name = html.escape(str(p.get("last_name", "")))
    username = html.escape(str(p.get("username", "немає")))
    user_id_esc = html.escape(str(target_uid))
    status_str = "<b>✅ В команді</b>" if is_app else "<b>❌ Не в команді</b>"

    info_text = (
        f"{action_msg}\n\n"
        f"<b>👤 Картка користувача:</b>\n"
        f"🆔 <b>ID:</b> <code>{user_id_esc}</code>\n"
        f"👤 <b>Ім'я:</b> {first_name} {last_name}\n"
        f"🏷️ <b>Username:</b> @{username}\n"
        f"Статус: {status_str}"
    )
    await message.answer(info_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@router.message(F.text.regexp(r"\((\d+)\)"))
async def handle_select_user_card(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    m = re.search(r"\((\d+)\)", message.text)
    if m:
        target_uid = m.group(1)
        target_u = await app.storage.load_user(target_uid)
        if target_u:
            user = await app.storage.load_user(chat_id)
            user["context_data"]["manage_user_id"] = target_uid
            user["state"] = "manage_user"
            await app.storage.save_user(user)

            is_app = target_u.get("is_approved", False)
            is_t_adm = await app.is_user_admin(target_uid)
            btn_team = "❌ Видалити з команди" if is_app else "✅ Додати в команду"
            btn_admin = "🔻 Забрати адміна" if is_t_adm else "👑 Призначити адміном"

            keyboard = ReplyKeyboardMarkup(keyboard=[
                [KeyboardButton(text=btn_team)],
                [KeyboardButton(text=btn_admin)],
                [KeyboardButton(text="Повернутись в адмінку")]
            ], resize_keyboard=True)

            p = target_u.get("personal", {})
            first_name = html.escape(str(p.get("first_name", "")))
            last_name = html.escape(str(p.get("last_name", "")))
            username = html.escape(str(p.get("username", "немає")))
            user_id_esc = html.escape(str(target_uid))
            status_str = "<b>✅ В команді</b>" if is_app else "<b>❌ Не в команді</b>"

            info_text = (
                f"<b>👤 Картка користувача:</b>\n"
                f"🆔 <b>ID:</b> <code>{user_id_esc}</code>\n"
                f"👤 <b>Ім'я:</b> {first_name} {last_name}\n"
                f"🏷️ <b>Username:</b> @{username}\n"
                f"Статус: {status_str}"
            )
            await message.answer(info_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
