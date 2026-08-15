"""Anti-flood middleware.

A lightweight in-process token check: a user who fires updates faster than the
configured interval is silently dropped, and warned once per burst. This keeps
the bot responsive without needing Redis for small deployments.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TelegramUser

from app.config import SecuritySettings
from app.utils.logging import get_logger

logger = get_logger(__name__)

THROTTLE_NOTICE = "⏳ Slow down a little, please."


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings
        self._last_seen: dict[int, float] = {}
        self._violations: dict[int, int] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.settings.rate_limit_enabled:
            return await handler(event, data)

        telegram_user: TelegramUser | None = data.get("event_from_user")
        if telegram_user is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_seen.get(telegram_user.id, 0.0)
        if now - last < self.settings.rate_limit_interval:
            count = self._violations.get(telegram_user.id, 0) + 1
            self._violations[telegram_user.id] = count
            if count == self.settings.rate_limit_burst:
                await self._warn(event)
            logger.debug("throttle.dropped", telegram_id=telegram_user.id, count=count)
            return None

        self._last_seen[telegram_user.id] = now
        self._violations.pop(telegram_user.id, None)
        self._prune(now)
        return await handler(event, data)

    async def _warn(self, event: TelegramObject) -> None:
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(THROTTLE_NOTICE, show_alert=False)
            elif isinstance(event, Message):
                await event.answer(THROTTLE_NOTICE)
        except Exception:  # pragma: no cover - warning is best effort
            pass

    def _prune(self, now: float, max_entries: int = 10_000) -> None:
        """Drop stale entries so the maps cannot grow without bound."""
        if len(self._last_seen) <= max_entries:
            return
        cutoff = now - 300
        self._last_seen = {
            user_id: seen for user_id, seen in self._last_seen.items() if seen > cutoff
        }
