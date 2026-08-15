"""Safe outbound message delivery.

Mass messaging is where a Telegram bot most often breaks: a single user who
blocked the bot must never abort a broadcast, and Telegram's flood limits have
to be respected. Everything that pushes messages to many chats goes through
:class:`MessageDispatcher`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup

from app.utils.logging import get_logger

logger = get_logger(__name__)

BlockedCallback = Callable[[int], Awaitable[None]]


@dataclass(slots=True)
class DeliveryResult:
    """Outcome of a single send attempt."""

    chat_id: int
    ok: bool
    error: str | None = None
    #: True when the chat is permanently unreachable (blocked/deleted account).
    blocked: bool = False


class MessageDispatcher:
    """Rate-limited, error-tolerant wrapper around ``Bot.send_*``."""

    def __init__(
        self,
        bot: Bot,
        *,
        messages_per_second: int = 20,
        on_blocked: BlockedCallback | None = None,
    ) -> None:
        self._bot = bot
        self._interval = 1 / max(messages_per_second, 1)
        self._on_blocked = on_blocked
        self._lock = asyncio.Lock()

    async def send(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        photo_file_id: str | None = None,
        disable_notification: bool = False,
    ) -> DeliveryResult:
        """Send one message, absorbing every Telegram error.

        Retries once when Telegram asks us to slow down; any other API error is
        reported back to the caller instead of raised.
        """
        for attempt in (1, 2):
            try:
                async with self._lock:
                    if photo_file_id:
                        await self._bot.send_photo(
                            chat_id,
                            photo=photo_file_id,
                            caption=text,
                            reply_markup=reply_markup,
                            disable_notification=disable_notification,
                        )
                    else:
                        await self._bot.send_message(
                            chat_id,
                            text,
                            reply_markup=reply_markup,
                            disable_notification=disable_notification,
                        )
                    await asyncio.sleep(self._interval)
                return DeliveryResult(chat_id=chat_id, ok=True)
            except TelegramRetryAfter as error:
                if attempt == 2:
                    return DeliveryResult(
                        chat_id=chat_id, ok=False, error="flood limit"
                    )
                logger.warning(
                    "telegram.flood_limit", chat_id=chat_id, retry_after=error.retry_after
                )
                await asyncio.sleep(error.retry_after + 1)
            except TelegramForbiddenError:
                if self._on_blocked:
                    await self._on_blocked(chat_id)
                return DeliveryResult(
                    chat_id=chat_id, ok=False, error="bot blocked", blocked=True
                )
            except TelegramBadRequest as error:
                message = str(error)
                # "chat not found" means the account is gone for good.
                blocked = "chat not found" in message.lower()
                if blocked and self._on_blocked:
                    await self._on_blocked(chat_id)
                return DeliveryResult(
                    chat_id=chat_id, ok=False, error=message[:200], blocked=blocked
                )
            except TelegramAPIError as error:  # pragma: no cover - network layer
                logger.error("telegram.api_error", chat_id=chat_id, error=str(error))
                return DeliveryResult(chat_id=chat_id, ok=False, error=str(error)[:200])
        return DeliveryResult(chat_id=chat_id, ok=False, error="unknown")

    async def send_many(
        self,
        chat_ids: list[int],
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        photo_file_id: str | None = None,
        progress: Callable[[list[DeliveryResult]], Awaitable[None]] | None = None,
        batch_size: int = 25,
    ) -> list[DeliveryResult]:
        """Send the same message to many chats, reporting progress per batch."""
        results: list[DeliveryResult] = []
        batch: list[DeliveryResult] = []
        for chat_id in chat_ids:
            result = await self.send(
                chat_id,
                text,
                reply_markup=reply_markup,
                photo_file_id=photo_file_id,
                disable_notification=True,
            )
            results.append(result)
            batch.append(result)
            if progress and len(batch) >= batch_size:
                await progress(batch)
                batch = []
        if progress and batch:
            await progress(batch)
        return results
