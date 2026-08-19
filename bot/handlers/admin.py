"""
Admin panel and user management handlers.
"""

import html

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from bot.keyboards import get_admin_keyboard
from config import ADMIN_CHAT_ID, logger

router = Router()


@router.message(F.text.lower().in_(["👑 адмінка", "адмінка", "повернутись в адмінку", "👑 admin panel", "admin panel", "back to admin"]))
async def handle_admin_panel(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    user["state"] = "idle"
    user["context_data"] = {}
    await app.storage.save_user(user)
    u_lang = user.get("language", "uk")
    await message.answer(
        "*👑 Панель Адміністратора*" if u_lang != "en" else "*👑 Admin Panel*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard(lang=u_lang),
    )


@router.message(F.text.lower().in_(["👥 користувачі", "користувачі", "👥 users", "users"]))
async def handle_list_approved_users(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    all_users = await app.storage.load_all_users()
    btn_list = []
    for uid, udata in all_users.items():
        if udata.get("is_approved") or await app.is_user_admin(uid):
            name = udata.get("personal", {}).get("first_name", "User")
            role = "👑" if await app.is_user_admin(uid) else "👤"
            btn_list.append([KeyboardButton(text=f"{role} {name} ({uid})")])
    btn_list.append([KeyboardButton(text="Повернутись в адмінку" if u_lang != "en" else "Back to admin")])
    await message.answer(
        "*Список затверджених користувачів:*" if u_lang != "en" else "*Approved users list:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard=btn_list, resize_keyboard=True),
    )


@router.message(F.text.lower().in_(["🆕 нові користувачі", "нові користувачі", "🆕 new users", "new users"]))
async def handle_list_pending_users(message: Message, app):
    chat_id = str(message.chat.id)
    if not await app.is_user_admin(chat_id):
        return

    all_users = await app.storage.load_all_users()
    user = await app.storage.load_user(chat_id)
    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    btn_list = []
    for uid, udata in all_users.items():
        if not udata.get("is_approved") and not await app.is_user_admin(uid):
            name = udata.get("personal", {}).get("first_name", "New" if is_en else "Новий")
            btn_list.append([KeyboardButton(text=f"⏳ {name} ({uid})")])
    if not btn_list:
        await message.answer(
            "*No pending users.*" if is_en else "*Немає нових користувачів.*",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    btn_list.append([KeyboardButton(text="Back to admin" if is_en else "Повернутись в адмінку")])
    await message.answer(
        "*Pending new users:*" if is_en else "*Нові користувачі на підтвердженні:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardMarkup(keyboard=btn_list, resize_keyboard=True),
    )


@router.message(
    F.text.in_(
        [
            "✅ Додати в команду",
            "❌ Видалити з команди",
            "👑 Призначити адміном",
            "🔻 Забрати адміна",
            "🗑️ Повністю видалити з бази",
            "✅ Add to Team",
            "❌ Remove from Team",
            "👑 Grant Admin",
            "🔻 Revoke Admin",
            "🗑️ Delete from Database"
        ]
    )
)
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

    u_lang = user.get("language", "uk")
    is_en = u_lang == "en"

    target_u = await app.storage.load_user(target_uid)
    action_msg = ""
    text = message.text

    if text in ["🗑️ Повністю видалити з бази", "🗑️ Delete from Database"]:
        if str(target_uid) == str(ADMIN_CHAT_ID):
            action_msg = "⚠️ Cannot delete the primary administrator!" if is_en else "⚠️ Неможливо видалити головного адміністратора!"
        else:
            ok = await app.storage.delete_user(target_uid)
            if ok:
                user["state"] = "idle"
                user["context_data"] = {}
                await app.storage.save_user(user)
                await message.answer(
                    f"🗑️ User <code>{html.escape(str(target_uid))}</code> deleted from database!" if is_en else f"🗑️ Користувача <code>{html.escape(str(target_uid))}</code> видалено з бази даних!",
                    parse_mode=ParseMode.HTML,
                    reply_markup=get_admin_keyboard(lang=u_lang),
                )
                return
            else:
                action_msg = f"⚠️ Could not delete user <code>{html.escape(str(target_uid))}</code>." if is_en else f"⚠️ Не вдалося видалити користувача <code>{html.escape(str(target_uid))}</code>."

    elif text in ["✅ Додати в команду", "✅ Add to Team"]:
        target_u["is_approved"] = True
        await app.storage.save_user(target_u)
        action_msg = f"✅ User <code>{html.escape(str(target_uid))}</code> added to team!" if is_en else f"✅ Користувача <code>{html.escape(str(target_uid))}</code> успішно додано в команду!"
        try:
            if app.bot:
                t_user = await app.storage.load_user(target_uid)
                t_lang = t_user.get("language", "uk")
                await app.bot.send_message(
                    chat_id=target_uid,
                    text="🎉 <b>Welcome! Administrator granted you access to 3D Farm!</b>\nPress /start to navigate to the main menu." if t_lang == "en" else "🎉 <b>Вітаємо! Адміністратор надав вам доступ до 3D Ферми!</b>\nНатисніть /start для переходу до головного меню.",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as e:
            logger.warning(f"Failed sending approval notification to {target_uid}: {e}")

    elif text in ["❌ Видалити з команди", "❌ Remove from Team"]:
        target_u["is_approved"] = False
        await app.storage.save_user(target_u)
        action_msg = f"❌ User <code>{html.escape(str(target_uid))}</code> removed from team!" if is_en else f"❌ Користувача <code>{html.escape(str(target_uid))}</code> видалено з команди!"

    elif text in ["👑 Призначити адміном", "👑 Grant Admin"]:
        if "admin" not in target_u:
            target_u["admin"] = {}
        target_u["admin"]["access_admin"] = True
        await app.storage.save_user(target_u)
        action_msg = f"👑 User <code>{html.escape(str(target_uid))}</code> granted admin rights!" if is_en else f"👑 Користувача <code>{html.escape(str(target_uid))}</code> призначено адміністратором!"

    elif text in ["🔻 Забрати адміна", "🔻 Revoke Admin"]:
        if str(target_uid) == str(ADMIN_CHAT_ID):
            action_msg = "⚠️ Cannot revoke admin rights from primary administrator!" if is_en else "⚠️ Неможливо забрати адмін-права у головного адміністратора!"
        else:
            if "admin" not in target_u:
                target_u["admin"] = {}
            target_u["admin"]["access_admin"] = False
            await app.storage.save_user(target_u)
            action_msg = f"🔻 Admin rights for <code>{html.escape(str(target_uid))}</code> revoked." if is_en else f"🔻 Адмін-права для <code>{html.escape(str(target_uid))}</code> скасовано."

    is_app = target_u.get("is_approved", False)
    is_t_adm = await app.is_user_admin(target_uid)
    if is_en:
        btn_team = "❌ Remove from Team" if is_app else "✅ Add to Team"
        btn_admin = "🔻 Revoke Admin" if is_t_adm else "👑 Grant Admin"
        btn_del = "🗑️ Delete from Database"
        btn_back = "Back to admin"
    else:
        btn_team = "❌ Видалити з команди" if is_app else "✅ Додати в команду"
        btn_admin = "🔻 Забрати адміна" if is_t_adm else "👑 Призначити адміном"
        btn_del = "🗑️ Повністю видалити з бази"
        btn_back = "Повернутись в адмінку"

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=btn_team)],
            [KeyboardButton(text=btn_admin)],
            [KeyboardButton(text=btn_del)],
            [KeyboardButton(text=btn_back)],
        ],
        resize_keyboard=True,
    )

    p = target_u.get("personal", {})
    first_name = html.escape(str(p.get("first_name", "")))
    last_name = html.escape(str(p.get("last_name", "")))
    username = html.escape(str(p.get("username", "none" if is_en else "немає")))
    user_id_esc = html.escape(str(target_uid))
    status_str = ("<b>✅ In Team</b>" if is_app else "<b>❌ Not in Team</b>") if is_en else ("<b>✅ В команді</b>" if is_app else "<b>❌ Не в команді</b>")
    adm_str = ("<b>👑 Administrator</b>" if is_t_adm else "<b>👤 User</b>") if is_en else ("<b>👑 Адміністратор</b>" if is_t_adm else "<b>👤 Користувач</b>")

    if is_en:
        info_text = (
            f"{action_msg}\n\n"
            f"<b>👤 User Card:</b>\n"
            f"🆔 <b>ID:</b> <code>{user_id_esc}</code>\n"
            f"👤 <b>Name:</b> {first_name} {last_name}\n"
            f"🏷️ <b>Username:</b> @{username}\n"
            f"Role: {adm_str}\n"
            f"Status: {status_str}"
        )
    else:
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
