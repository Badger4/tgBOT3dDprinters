"""
Persistent Notification Outbox Dispatcher with rate limiting and exponential backoff.
Guarantees reliable Telegram alert delivery during network drops, power flickers, and 429 rate limits.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from config import logger


class NotificationOutboxDispatcher:
    """Dispatches notifications from SQLite outbox with rate-limiting, retry queues, and backoff."""

    def __init__(self, bot: Bot | None, storage: Any) -> None:
        self.bot = bot
        self.storage = storage
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_send_ts = 0.0
        self._last_chat_send_ts: dict[str, float] = {}
        self._chat_blocked_until: dict[str, float] = {}
        self._global_blocked_until = 0.0
        self._last_purge_ts = 0.0
        self._new_item_event: asyncio.Event | None = None

    def start(self) -> None:
        """Starts the background dispatcher loop if bot is active."""
        if not self.bot or self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._new_item_event = asyncio.Event()
            self._task = loop.create_task(self._dispatcher_loop())
            logger.info("📬 Started Telegram Notification Outbox Dispatcher")
        except RuntimeError:
            pass

    async def stop(self) -> None:
        """Stops the dispatcher loop gracefully."""
        self._running = False
        if self._new_item_event:
            self._new_item_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("📭 Stopped Telegram Notification Outbox Dispatcher")

    async def enqueue(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = ParseMode.HTML,
        reply_markup: Any | None = None,
        delay_sec: float = 0.0,
    ) -> int:
        """Enqueues a message into persistent SQLite outbox."""
        markup_json = None
        if reply_markup is not None:
            try:
                if hasattr(reply_markup, "model_dump_json"):
                    markup_json = reply_markup.model_dump_json()
                elif hasattr(reply_markup, "to_python"):
                    markup_json = json.dumps(reply_markup.to_python())
                elif isinstance(reply_markup, dict):
                    markup_json = json.dumps(reply_markup)
            except Exception as e:
                logger.warning(f"Failed serializing reply_markup for outbox: {e}")

        msg_id = await self.storage.enqueue_outbox_message(
            chat_id=str(chat_id),
            text=text,
            parse_mode=parse_mode,
            reply_markup_json=markup_json,
            delay_sec=delay_sec,
        )

        if self._new_item_event:
            self._new_item_event.set()

        return msg_id

    async def _dispatcher_loop(self) -> None:
        """Main consumer loop draining outbox with rate-limiting."""
        while self._running:
            try:
                # 0. Check global rate limit backoff (e.g. from 429)
                now_t = time.time()
                if now_t < self._global_blocked_until:
                    wait_time = min(30.0, self._global_blocked_until - now_t)
                    await asyncio.sleep(max(0.1, wait_time))
                    continue

                # Periodic purge of sent/failed records (every 6 hours)
                if now_t - self._last_purge_ts > 21600.0:
                    self._last_purge_ts = now_t
                    try:
                        await self.storage.purge_old_outbox(max_age_days=7)
                    except Exception:
                        pass

                # Fetch next batch of pending messages
                batch = await self.storage.fetch_pending_outbox_messages(limit=10)
                if not batch:
                    # Reactive wait: wake up immediately when a new message is enqueued, or after 5s for retries
                    if self._new_item_event:
                        self._new_item_event.clear()
                        try:
                            await asyncio.wait_for(self._new_item_event.wait(), timeout=5.0)
                        except asyncio.TimeoutError:
                            pass
                    else:
                        await asyncio.sleep(1.0)
                    continue

                for msg in batch:
                    if not self._running:
                        break

                    chat_id = str(msg["chat_id"])
                    msg_id = int(msg["id"])
                    attempts = int(msg.get("attempts", 0))

                    # 1. Check if chat is temporarily blocked by TelegramRetryAfter
                    now_t = time.time()
                    if now_t < self._chat_blocked_until.get(chat_id, 0.0):
                        remaining = self._chat_blocked_until[chat_id] - now_t
                        await self.storage.mark_outbox_retry(msg_id, delay_sec=max(1.0, remaining), attempts=attempts)
                        continue

                    # 2. Enforce per-chat rate limit (min 1.0s between sends to same user)
                    last_chat = self._last_chat_send_ts.get(chat_id, 0.0)
                    now_mono = time.monotonic()
                    if now_mono - last_chat < 1.0:
                        wait_chat = 1.0 - (now_mono - last_chat)
                        if wait_chat > 0:
                            await asyncio.sleep(wait_chat)

                    # 3. Enforce global rate limit (max 25 msgs/sec -> min 0.04s between sends)
                    now_mono = time.monotonic()
                    if now_mono - self._last_send_ts < 0.04:
                        await asyncio.sleep(0.04)

                    # 4. Check if user has blocked bot
                    user = None
                    if hasattr(self.storage, "load_user"):
                        try:
                            user = await self.storage.load_user(chat_id)
                        except Exception:
                            user = None

                    if user and user.get("chat_active") is False:
                        await self.storage.mark_outbox_failed(msg_id, reason="User chat inactive")
                        continue

                    # 5. Reconstruct reply markup
                    reply_markup = None
                    markup_raw = msg.get("reply_markup_json")
                    if markup_raw:
                        try:
                            m_dict = json.loads(markup_raw)
                            if "inline_keyboard" in m_dict:
                                reply_markup = InlineKeyboardMarkup.model_validate(m_dict)
                            elif "keyboard" in m_dict:
                                reply_markup = ReplyKeyboardMarkup.model_validate(m_dict)
                        except Exception:
                            pass

                    # 6. Send message with full exception taxonomy
                    try:
                        if not self.bot:
                            break
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=msg["text"],
                            parse_mode=msg.get("parse_mode") or ParseMode.HTML,
                            reply_markup=reply_markup,
                        )
                        self._last_send_ts = time.monotonic()
                        self._last_chat_send_ts[chat_id] = self._last_send_ts
                        await self.storage.mark_outbox_success(msg_id)

                    except TelegramRetryAfter as e:
                        retry_sec = float(e.retry_after)
                        logger.warning(f"⏳ [Outbox] Rate limit for {chat_id}. Pausing {retry_sec}s.")
                        pause_until = time.time() + retry_sec + 0.5
                        self._chat_blocked_until[chat_id] = pause_until
                        self._global_blocked_until = pause_until
                        await self.storage.mark_outbox_retry(msg_id, delay_sec=retry_sec + 0.5, attempts=attempts + 1)
                        # Sleep globally so we don't bombard Telegram further
                        await asyncio.sleep(min(30.0, retry_sec + 0.1))
                        break  # Break inner batch loop to let backoff settle

                    except TelegramForbiddenError as e:
                        logger.info(f"🚫 [Outbox] Bot was blocked by {chat_id}: {e}")
                        if user and hasattr(self.storage, "save_user"):
                            user["chat_active"] = False
                            await self.storage.save_user(user)
                        await self.storage.mark_outbox_failed(msg_id, reason=str(e))

                    except TelegramBadRequest as e:
                        err_str = str(e).lower()
                        if "chat not found" in err_str or "user is deactivated" in err_str:
                            logger.info(f"🚫 [Outbox] Inactive user {chat_id}: {e}")
                            if user and hasattr(self.storage, "save_user"):
                                user["chat_active"] = False
                                await self.storage.save_user(user)
                            await self.storage.mark_outbox_failed(msg_id, reason=str(e))
                        else:
                            logger.warning(f"⚠️ [Outbox] Bad request for {chat_id}: {e}")
                            await self.storage.mark_outbox_failed(msg_id, reason=str(e))

                    except (TelegramNetworkError, aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                        delay = min(300.0, (2 ** min(attempts, 8)) + 3.0)
                        logger.warning(f"📡 [Outbox] Network drop to {chat_id} ({e}). Retrying in {delay:.1f}s.")
                        await self.storage.mark_outbox_retry(msg_id, delay_sec=delay, attempts=attempts + 1)

                    except Exception as e:
                        if attempts >= 5:
                            logger.error(f"❌ [Outbox] Permanent failure after 5 attempts to {chat_id}: {e}")
                            await self.storage.mark_outbox_failed(msg_id, reason=str(e))
                        else:
                            logger.warning(f"⚠️ [Outbox] Error sending to {chat_id}: {e}. Retrying.")
                            await self.storage.mark_outbox_retry(msg_id, delay_sec=10.0, attempts=attempts + 1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in outbox loop: {e}")
                await asyncio.sleep(2.0)
