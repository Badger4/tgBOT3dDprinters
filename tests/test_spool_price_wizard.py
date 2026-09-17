import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from bot.keyboards import get_spool_price_keyboard
from bot.handlers.filament.add import handle_filament_states


def test_get_spool_price_keyboard_structure():
    kb_1kg_uk = get_spool_price_keyboard(1000.0, lang="uk")
    assert any("Ціна за всю котушку" in btn.text for row in kb_1kg_uk.keyboard for btn in row)
    assert any("Крок назад" in btn.text for row in kb_1kg_uk.keyboard for btn in row)

    kb_3kg_uk = get_spool_price_keyboard(3000.0, lang="uk")
    assert any("Ціна за всю котушку (3 кг)" in btn.text for row in kb_3kg_uk.keyboard for btn in row)

    kb_3kg_en = get_spool_price_keyboard(3000.0, lang="en")
    assert any("Price for entire spool (3 kg)" in btn.text for row in kb_3kg_en.keyboard for btn in row)


@pytest.mark.asyncio
async def test_add_spool_grams_shows_hint_for_3kg():
    user = {
        "chat_id": "123",
        "language": "uk",
        "state": "add_spool_grams",
        "context_data": {"new_spool": {"name": "Test Spool", "type": "PLA", "color": "#000000"}}
    }
    app = MagicMock()
    app.storage = MagicMock()
    app.storage.load_user = AsyncMock(return_value=user)
    app.storage.save_user = AsyncMock()

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat, id=123)
    message.from_user = MagicMock(spec=User, id=123, username="testuser")
    message.text = "3000g"
    message.answer = AsyncMock()

    handled = await handle_filament_states(message, app)
    assert handled is True
    assert user["state"] == "add_spool_price"
    assert user["context_data"]["new_spool"]["remaining_grams"] == 3000.0

    call_args = message.answer.call_args
    prompt_text = call_args[0][0]
    assert "1500/3" in prompt_text
    assert "3 кг" in prompt_text
    assert "Ціна за всю котушку" in prompt_text


@pytest.mark.asyncio
async def test_add_spool_price_formula_division():
    user = {
        "chat_id": "123",
        "language": "uk",
        "state": "add_spool_price",
        "context_data": {"new_spool": {"name": "Test Spool", "type": "PLA", "remaining_grams": 3000.0}}
    }
    app = MagicMock()
    app.storage = MagicMock()
    app.storage.load_user = AsyncMock(return_value=user)
    app.storage.save_user = AsyncMock()

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat, id=123)
    message.from_user = MagicMock(spec=User, id=123, username="testuser")
    message.text = "1500 / 3 грн"
    message.answer = AsyncMock()

    handled = await handle_filament_states(message, app)
    assert handled is True
    assert user["state"] == "add_spool_quantity"
    assert user["context_data"]["new_spool"]["price_per_kg"] == 500.0


@pytest.mark.asyncio
async def test_add_spool_total_price_button_and_calculation():
    user = {
        "chat_id": "123",
        "language": "uk",
        "state": "add_spool_price",
        "context_data": {"new_spool": {"name": "Test Spool", "type": "PLA", "remaining_grams": 3000.0}}
    }
    app = MagicMock()
    app.storage = MagicMock()
    app.storage.load_user = AsyncMock(return_value=user)
    app.storage.save_user = AsyncMock()

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat, id=123)
    message.from_user = MagicMock(spec=User, id=123, username="testuser")
    message.text = "🏷️ Ціна за всю котушку (3 кг)"
    message.answer = AsyncMock()

    # Step 1: Click total price button
    handled = await handle_filament_states(message, app)
    assert handled is True
    assert user["state"] == "add_spool_total_price"
    prompt_text = message.answer.call_args[0][0]
    assert "Введіть вартість усієї котушки" in prompt_text
    assert "3000г" in prompt_text

    # Step 2: Enter 1500 грн
    message.text = "1500 грн"
    message.answer.reset_mock()
    handled2 = await handle_filament_states(message, app)
    assert handled2 is True
    assert user["state"] == "add_spool_quantity"
    assert user["context_data"]["new_spool"]["price_per_kg"] == 500.0
    ans_text = message.answer.call_args[0][0]
    assert "500 грн/кг" in ans_text
    assert "1500 грн" in ans_text


@pytest.mark.asyncio
async def test_step_back_from_total_price():
    user = {
        "chat_id": "123",
        "language": "uk",
        "state": "add_spool_total_price",
        "context_data": {"new_spool": {"name": "Test Spool", "remaining_grams": 3000.0}}
    }
    app = MagicMock()
    app.storage = MagicMock()
    app.storage.load_user = AsyncMock(return_value=user)
    app.storage.save_user = AsyncMock()

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat, id=123)
    message.from_user = MagicMock(spec=User, id=123, username="testuser")
    message.text = "↩️ Крок назад"
    message.answer = AsyncMock()

    handled = await handle_filament_states(message, app)
    assert handled is True
    assert user["state"] == "add_spool_price"
    ans_text = message.answer.call_args[0][0]
    assert "Введіть ціну за 1 кг у грн" in ans_text
