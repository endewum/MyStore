"""Database session + service container middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

from app.config import Settings
from app.database.session import Database
from app.services.registry import Services


class DatabaseMiddleware(BaseMiddleware):
    """Open one transaction per update and expose the service container.

    Committing here (rather than inside handlers) gives every update a clean
    unit of work: either all of its writes land, or none do.
    """

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot | None = data.get("bot")
        async with self.database.session() as session:
            data["session"] = session
            data["db"] = self.database
            data["settings"] = self.settings
            data["services"] = Services(session, self.settings, bot)
            return await handler(event, data)
