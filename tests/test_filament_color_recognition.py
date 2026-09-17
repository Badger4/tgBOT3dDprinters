import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from utils.filament_utils import parse_filament_color, get_color_display_name, get_color_emoji
from bot.keyboards import get_filament_colors_keyboard
from bot.handlers.filament.add import handle_filament_states


def test_parse_extended_filament_colors():
    # 1. Turquoise / Бірюзовий
    hex_code, name = parse_filament_color("бірюзовий")
    assert hex_code == "#0D9488"
    assert name == "Бірюзовий"

    hex_code, name = parse_filament_color("Бірюза")
    assert hex_code == "#0D9488"

    # 2. Khaki / Хакі
    hex_code, name = parse_filament_color("хакі")
    assert hex_code == "#556B2F"
    assert name == "Хакі"

    # 3. Graphite / Графіт
    hex_code, name = parse_filament_color("графіт")
    assert hex_code == "#374151"
    assert name == "Графітовий"

    # 4. Burgundy / Бордовий
    hex_code, name = parse_filament_color("бордовий")
    assert hex_code == "#991B1B"
    assert name == "Бордовий"

    # 5. Mint / М'ятний
    hex_code, name = parse_filament_color("м'ятний")
    assert hex_code == "#2DD4BF"
    assert name == "М'ятний"

    # 6. Lavender / Лавандовий
    hex_code, name = parse_filament_color("лаванда")
    assert hex_code == "#A855F7"


def test_custom_color_name_preserved():
    # Even with generic or random hex, user's custom color name MUST be preserved
    disp1 = get_color_display_name({"color": "#3B82F6", "color_name": "Бірюзовий"})
    assert "Бірюзовий" in disp1
    assert "Синій" not in disp1

    disp2 = get_color_display_name({"color": "#0D9488", "color_name": "Морська хвиля"})
    assert "Морська хвиля" in disp2

    disp3 = get_color_display_name({"color": "#556B2F", "color_name": "Хакі"})
    assert "Хакі" in disp3


def test_compact_keyboard_structure():
    kb = get_filament_colors_keyboard(lang="uk")
    # Should have 2 rows of 4 buttons (8 colors total) + navigation row
    assert len(kb.keyboard) == 3
    assert len(kb.keyboard[0]) == 4
    assert len(kb.keyboard[1]) == 4
    all_texts = [btn.text for row in kb.keyboard for btn in row]
    assert "⚫ Чорний" in all_texts
    assert "⚪ Білий" in all_texts
    assert "🔵 Синій" in all_texts
    assert "↩️ Крок назад" in all_texts


@pytest.mark.asyncio
async def test_add_spool_color_text_input_turquoise():
    user = {
        "chat_id": "123",
        "language": "uk",
        "state": "add_spool_color",
        "context_data": {"new_spool": {"name": "Test Spool", "type": "PLA"}}
    }
    app = MagicMock()
    app.storage = MagicMock()
    app.storage.load_user = AsyncMock(return_value=user)
    app.storage.save_user = AsyncMock()

    message = MagicMock(spec=Message)
    message.chat = MagicMock(spec=Chat, id=123)
    message.from_user = MagicMock(spec=User, id=123, username="testuser")
    message.text = "бірюзовий"
    message.answer = AsyncMock()

    handled = await handle_filament_states(message, app)
    assert handled is True
    assert user["state"] == "add_spool_grams"
    assert user["context_data"]["new_spool"]["color"] == "#0D9488"
    assert user["context_data"]["new_spool"]["color_name"] == "Бірюзовий"

    ans_text = message.answer.call_args[0][0]
    assert "Бірюзовий" in ans_text
    assert "Синій" not in ans_text
