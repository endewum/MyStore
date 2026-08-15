"""Middlewares and their registration order."""

from __future__ import annotations

from aiogram import Dispatcher

from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.errors import ErrorMiddleware
from app.bot.middlewares.throttling import ThrottlingMiddleware
from app.bot.middlewares.user import UserMiddleware
from app.config import Settings
from app.database.session import Database


def register_middlewares(
    dispatcher: Dispatcher, database: Database, settings: Settings
) -> None:
    """Install middlewares outermost-first for messages and callbacks.

    They are registered as **outer** middlewares because filters
    (``IsAdmin``) are evaluated before inner middlewares run: only outer
    middlewares can put ``session``, ``user`` and ``admin`` into the handler
    data early enough for authorization filters to see them.

    Order matters: errors are caught outside the transaction, throttling runs
    before any database work, and user resolution needs the session.
    """
    layers = (
        ErrorMiddleware(),
        ThrottlingMiddleware(settings.security),
        DatabaseMiddleware(database, settings),
        UserMiddleware(),
    )
    for layer in layers:
        dispatcher.message.outer_middleware(layer)
        dispatcher.callback_query.outer_middleware(layer)


__all__ = [
    "DatabaseMiddleware",
    "ErrorMiddleware",
    "ThrottlingMiddleware",
    "UserMiddleware",
    "register_middlewares",
]
