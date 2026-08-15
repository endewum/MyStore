"""Error translation middleware.

Expected business errors (:class:`~app.services.exceptions.ServiceError`) are
turned into short, friendly messages. Unexpected errors are logged with context
and the user gets a generic apology instead of a silent failure.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.exc import SQLAlchemyError

from app.services.exceptions import ServiceError
from app.utils.logging import get_logger

logger = get_logger(__name__)

GENERIC_ERROR = "⚠️ Something went wrong. Please try again in a moment."
DB_ERROR = "⚠️ The store is busy right now. Please try again shortly."


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except ServiceError as error:
            await self._notify(event, f"⚠️ {error.message}")
        except SQLAlchemyError as error:
            logger.error("database.error", error=str(error), exc_info=True)
            await self._notify(event, DB_ERROR)
        except TelegramBadRequest as error:
            # "message is not modified" happens when a user taps the same
            # button twice; it is noise, not a failure.
            if "message is not modified" in str(error).lower():
                if isinstance(event, CallbackQuery):
                    await self._safe_answer(event)
                return None
            logger.warning("telegram.bad_request", error=str(error))
            await self._notify(event, GENERIC_ERROR)
        except Exception as error:  # pragma: no cover - last line of defence
            logger.error("handler.unhandled", error=str(error), exc_info=True)
            await self._notify(event, GENERIC_ERROR)
        return None

    async def _notify(self, event: TelegramObject, text: str) -> None:
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(text)
        except Exception:  # pragma: no cover - nothing else we can do
            logger.warning("error_notice.failed")

    async def _safe_answer(self, event: CallbackQuery) -> None:
        try:
            await event.answer()
        except Exception:  # pragma: no cover
            pass
