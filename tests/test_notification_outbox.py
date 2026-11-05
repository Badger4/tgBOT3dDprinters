import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from services.notification_outbox import NotificationOutboxDispatcher
from storage.manager import StorageManager


@pytest.fixture
async def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageManager(base_dir=tmpdir)
        yield storage


@pytest.mark.asyncio
async def test_outbox_enqueue_and_success(temp_storage):
    mock_bot = AsyncMock()
    mock_bot.send_message.return_value = MagicMock(message_id=101)

    dispatcher = NotificationOutboxDispatcher(mock_bot, temp_storage)

    # 1. Enqueue message
    msg_id = await dispatcher.enqueue(
        chat_id="123456",
        text="<b>Print Finished!</b>",
        parse_mode=ParseMode.HTML,
    )
    assert msg_id > 0

    # 2. Check pending
    pending = await temp_storage.fetch_pending_outbox_messages(limit=10)
    assert len(pending) == 1
    assert pending[0]["chat_id"] == "123456"
    assert pending[0]["text"] == "<b>Print Finished!</b>"

    # 3. Run dispatcher loop for 1 tick
    dispatcher.start()
    await asyncio.sleep(0.3)
    await dispatcher.stop()

    # 4. Verify message sent
    assert mock_bot.send_message.called
    args, kwargs = mock_bot.send_message.call_args
    assert kwargs["chat_id"] == "123456"
    assert kwargs["text"] == "<b>Print Finished!</b>"

    # 5. Verify marked as sent in DB
    pending_after = await temp_storage.fetch_pending_outbox_messages(limit=10)
    assert len(pending_after) == 0


@pytest.mark.asyncio
async def test_outbox_retry_after_backoff(temp_storage):
    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = TelegramRetryAfter(
        method=MagicMock(),
        message="Too many requests",
        retry_after=1,
    )

    dispatcher = NotificationOutboxDispatcher(mock_bot, temp_storage)
    msg_id = await dispatcher.enqueue(chat_id="999", text="Alert 429")

    dispatcher.start()
    await asyncio.sleep(0.2)
    await dispatcher.stop()

    # Should have attempted once and rescheduled for future
    conn = temp_storage._get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, attempts, next_retry_ts FROM notification_outbox WHERE id = ?", (msg_id,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "pending"
    assert row[1] >= 1
    assert row[2] > time.time()  # Scheduled in future


@pytest.mark.asyncio
async def test_outbox_forbidden_marks_failed_and_deactivates_user(temp_storage):
    # Setup user in storage with user_id
    await temp_storage.save_user({"user_id": "888", "chat_id": "888", "chat_active": True, "is_approved": True})

    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = TelegramForbiddenError(
        method=MagicMock(),
        message="Forbidden: bot was blocked by the user",
    )

    dispatcher = NotificationOutboxDispatcher(mock_bot, temp_storage)
    msg_id = await dispatcher.enqueue(chat_id="888", text="Alert")

    dispatcher.start()
    await asyncio.sleep(0.2)
    await dispatcher.stop()

    conn = temp_storage._get_db()
    cur = conn.cursor()
    cur.execute("SELECT status FROM notification_outbox WHERE id = ?", (msg_id,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "failed"

    # Verify user was marked inactive
    user = await temp_storage.load_user("888")
    assert user.get("chat_active") is False


@pytest.mark.asyncio
async def test_outbox_network_error_exponential_backoff(temp_storage):
    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = TelegramNetworkError(
        method=MagicMock(),
        message="Connection reset by peer",
    )

    dispatcher = NotificationOutboxDispatcher(mock_bot, temp_storage)
    msg_id = await dispatcher.enqueue(chat_id="777", text="Network test")

    dispatcher.start()
    await asyncio.sleep(0.2)
    await dispatcher.stop()

    conn = temp_storage._get_db()
    cur = conn.cursor()
    cur.execute("SELECT status, attempts, next_retry_ts FROM notification_outbox WHERE id = ?", (msg_id,))
    row = cur.fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "pending"
    assert row[1] == 1
    assert row[2] > time.time()
