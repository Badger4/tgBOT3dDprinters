import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User

from bot.handlers.admin import (
    handle_admin_panel,
    handle_list_approved_users,
    handle_list_pending_users,
    handle_select_user,
    handle_manage_user_action,
)


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.storage = MagicMock()
    app.bot = AsyncMock()

    users_db = {
        "877001503": {
            "user_id": "877001503",
            "is_approved": True,
            "admin": {"access_admin": True},
            "personal": {"first_name": "Boss", "last_name": "Admin", "username": "boss"},
            "state": "idle",
            "context_data": {},
            "language": "uk",
        },
        "123456": {
            "user_id": "123456",
            "is_approved": False,
            "admin": {"access_admin": False},
            "personal": {"first_name": "Ivan", "last_name": "Petrov", "username": "ivan123"},
            "state": "idle",
            "context_data": {},
            "language": "uk",
        }
    }

    async def load_all_users():
        return users_db

    async def load_user(uid):
        return users_db.get(str(uid), {"user_id": str(uid), "personal": {}, "admin": {}, "state": "idle", "context_data": {}})

    async def save_user(u):
        users_db[str(u["user_id"])] = u
        return True

    async def delete_user(uid):
        users_db.pop(str(uid), None)
        return True

    async def is_user_admin(uid):
        u = users_db.get(str(uid))
        return bool(u and u.get("admin", {}).get("access_admin"))

    app.storage.load_all_users = AsyncMock(side_effect=load_all_users)
    app.storage.load_user = AsyncMock(side_effect=load_user)
    app.storage.save_user = AsyncMock(side_effect=save_user)
    app.storage.delete_user = AsyncMock(side_effect=delete_user)
    app.is_user_admin = AsyncMock(side_effect=is_user_admin)

    return app


@pytest.mark.asyncio
async def test_admin_select_user_flow(mock_app):
    admin_msg = MagicMock(spec=Message)
    admin_msg.chat = Chat(id=877001503, type="private")
    admin_msg.from_user = User(id=877001503, is_bot=False, first_name="Boss")
    admin_msg.answer = AsyncMock()

    # 1. Admin lists users
    admin_msg.text = "👥 Користувачі"
    await handle_list_approved_users(admin_msg, mock_app)
    assert admin_msg.answer.called
    reply_markup = admin_msg.answer.call_args[1]["reply_markup"]
    buttons = [b.text for row in reply_markup.keyboard for b in row]
    assert any("877001503" in b for b in buttons)

    # 2. Admin clicks on user button
    admin_msg.answer.reset_mock()
    admin_msg.text = "⏳ Ivan (123456)"
    await handle_select_user(admin_msg, mock_app)

    assert admin_msg.answer.called
    sent_text = admin_msg.answer.call_args[0][0]
    assert "Картка користувача" in sent_text
    assert "123456" in sent_text
    assert "Ivan" in sent_text

    # Check state was set to manage_user
    admin_user = await mock_app.storage.load_user("877001503")
    assert admin_user["state"] == "manage_user"
    assert admin_user["context_data"]["manage_user_id"] == "123456"

    # Check keyboard has management buttons
    card_markup = admin_msg.answer.call_args[1]["reply_markup"]
    card_buttons = [b.text for row in card_markup.keyboard for b in row]
    assert "✅ Додати в команду" in card_buttons
    assert "👑 Призначити адміном" in card_buttons
    assert "🗑️ Повністю видалити з бази" in card_buttons
    assert "Повернутись в адмінку" in card_buttons

    # 3. Admin clicks "✅ Додати в команду"
    admin_msg.answer.reset_mock()
    admin_msg.text = "✅ Додати в команду"
    await handle_manage_user_action(admin_msg, mock_app)

    target_u = await mock_app.storage.load_user("123456")
    assert target_u["is_approved"] is True
    assert "успішно додано в команду" in admin_msg.answer.call_args[0][0]

    # 4. Admin clicks "👑 Призначити адміном"
    admin_msg.answer.reset_mock()
    admin_msg.text = "👑 Призначити адміном"
    await handle_manage_user_action(admin_msg, mock_app)

    target_u = await mock_app.storage.load_user("123456")
    assert target_u["admin"]["access_admin"] is True
    assert "призначено адміністратором" in admin_msg.answer.call_args[0][0]

    # 5. Admin clicks "🔻 Забрати адміна"
    admin_msg.answer.reset_mock()
    admin_msg.text = "🔻 Забрати адміна"
    await handle_manage_user_action(admin_msg, mock_app)

    target_u = await mock_app.storage.load_user("123456")
    assert target_u["admin"]["access_admin"] is False
    assert "скасовано" in admin_msg.answer.call_args[0][0]

    # 6. Admin clicks "Повернутись в адмінку"
    admin_msg.answer.reset_mock()
    admin_msg.text = "Повернутись в адмінку"
    await handle_admin_panel(admin_msg, mock_app)

    admin_user = await mock_app.storage.load_user("877001503")
    assert admin_user["state"] == "idle"
    assert admin_user["context_data"] == {}
    assert "Панель Адміністратора" in admin_msg.answer.call_args[0][0]
