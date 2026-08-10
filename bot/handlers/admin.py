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

@router.message(F.text.in_(["✅ Додати в команду", "❌ Видалити з команди", "👑 Призначити адміном", "🔻 Забрати адміна", "🗑️ Повністю видалити з бази"]))
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

    if text == "🗑️ Повністю видалити з бази":
        if str(target_uid) == str(ADMIN_CHAT_ID):
            action_msg = "⚠️ Неможливо видалити головного адміністратора!"
        else:
            ok = await app.storage.delete_user(target_uid)
            if ok:
                user["state"] = "idle"
                user["context_data"] = {}
                await app.storage.save_user(user)
                await message.answer(
                    f"🗑️ Користувача <code>{html.escape(str(target_uid))}</code> видалено з бази даних!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_keyboard()
                )
                return
            else:
                action_msg = f"⚠️ Не вдалося видалити користувача <code>{html.escape(str(target_uid))}</code>."

    elif text == "✅ Додати в команду":
        target_u["is_approved"] = True
        await app.storage.save_user(target_u)
        action_msg = f"✅ Користувача <code>{html.escape(str(target_uid))}</code> успішно додано в команду! 😤"
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
        [KeyboardButton(text="🗑️ Повністю видалити з бази")],
        [KeyboardButton(text="Повернутись в адмінку")]
    ], resize_keyboard=True)

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Схвалити" if not is_app else "❌ Забрати доступ", callback_data=f"{'approve' if not is_app else 'reject'}_user_{target_uid}"),
            InlineKeyboardButton(text="👑 Призначити адміном" if not is_t_adm else "🔻 Забрати адміна", callback_data=f"{'make_admin' if not is_t_adm else 'reject'}_user_{target_uid}")
        ],
        [
            InlineKeyboardButton(text="🗑️ Видалити з бази", callback_data=f"delete_user_{target_uid}")
        ]
    ])

    p = target_u.get("personal", {})
    first_name = html.escape(str(p.get("first_name", "")))
    last_name = html.escape(str(p.get("last_name", "")))
    username = html.escape(str(p.get("username", "немає")))
    user_id_esc = html.escape(str(target_uid))
    status_str = "<b>✅ В команді</b>" if is_app else "<b>❌ Не в команді</b>"
    adm_str = "<b>👑 Адміністратор</b>" if is_t_adm else "<b>👤 Користувач</b>"

    info_text = (
        f"{action_msg}\n\n"
        f"<b>👤 Картка користувача:</b>\n"
        f"🆔 <b>ID:</b> <code>{user_id_esc}</code>\n"
        f"👤 <b>Ім'я:</b> {first_name} {last_name}\n"
        f"🏷️ <b>Username:</b> @{username}\n"
        f"Роль: {adm_str}\n"
        f"Статус: {status_str}"
    )
    await message.answer(info_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@router.message(F.text & F.text.func(lambda txt: bool(re.search(r"\((\d+)\)", txt or ""))))
async def handle_select_user_card(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    m = re.search(r"\((\d+)\)", message.text or "")
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
                [KeyboardButton(text="🗑️ Повністю видалити з бази")],
                [KeyboardButton(text="Повернутись в адмінку")]
            ], resize_keyboard=True)

            inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Схвалити" if not is_app else "❌ Забрати доступ", callback_data=f"{'approve' if not is_app else 'reject'}_user_{target_uid}"),
                    InlineKeyboardButton(text="👑 Призначити адміном" if not is_t_adm else "🔻 Забрати адміна", callback_data=f"{'make_admin' if not is_t_adm else 'reject'}_user_{target_uid}")
                ],
                [
                    InlineKeyboardButton(text="🗑️ Повністю видалити з бази", callback_data=f"delete_user_{target_uid}")
                ]
            ])

            p = target_u.get("personal", {})
            first_name = html.escape(str(p.get("first_name", "")))
            last_name = html.escape(str(p.get("last_name", "")))
            username = html.escape(str(p.get("username", "немає")))
            user_id_esc = html.escape(str(target_uid))
            status_str = "<b>✅ В команді</b>" if is_app else "<b>❌ Не в команді</b>"
            adm_str = "<b>👑 Адміністратор</b>" if is_t_adm else "<b>👤 Користувач</b>"

            info_text = (
                f"<b>👤 Картка користувача:</b>\n"
                f"🆔 <b>ID:</b> <code>{user_id_esc}</code>\n"
                f"👤 <b>Ім'я:</b> {first_name} {last_name}\n"
                f"🏷️ <b>Username:</b> @{username}\n"
                f"Роль: {adm_str}\n"
                f"Статус: {status_str}"
            )
            await message.answer(info_text, parse_mode=ParseMode.HTML, reply_markup=keyboard, reply_markup_inline=None)
            await message.answer("Швидкі дії:", reply_markup=inline_kb)
