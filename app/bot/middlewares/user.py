"""User registration / authorization middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TelegramUser

from app.services.registry import Services
from app.utils.logging import get_logger

logger = get_logger(__name__)

BLOCKED_NOTICE = (
    "🚫 Your account has been suspended.\n\n"
    "If you believe this is a mistake, please contact support."
)


class UserMiddleware(BaseMiddleware):
    """Attach the database ``User`` and ``Admin`` records to handler data.

    Admin status always comes from the database (Telegram ID + role), never
    from the username, so renaming an account cannot grant privileges.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user: TelegramUser | None = data.get("event_from_user")
        services: Services | None = data.get("services")
        if telegram_user is None or services is None or telegram_user.is_bot:
            return await handler(event, data)

        user = await services.users.register(telegram_user)
        data["user"] = user
        data["admin"] = await services.users.get_admin(telegram_user.id)

        if user.is_blocked:
            await self._reject(event)
            return None
        return await handler(event, data)

    async def _reject(self, event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(BLOCKED_NOTICE, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(BLOCKED_NOTICE)
