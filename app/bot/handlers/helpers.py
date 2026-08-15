"""Shared handler utilities."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.utils.logging import get_logger

logger = get_logger(__name__)


async def render(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    *,
    answer_text: str | None = None,
    alert: bool = False,
) -> None:
    """Show a screen, editing in place when the event is a button tap.

    Editing keeps the chat clean instead of appending a new message for every
    navigation step. Messages carrying media cannot be edited into plain text,
    so those fall back to sending a new message.
    """
    if isinstance(event, CallbackQuery):
        await answer_callback(event, answer_text, alert=alert)
        message = event.message
        if message is None:
            return
        try:
            if message.content_type != "text":
                await message.answer(text, reply_markup=keyboard)
                return
            await message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" in str(error).lower():
                return
            logger.debug("render.edit_failed", error=str(error))
            await message.answer(text, reply_markup=keyboard)
        return
    await event.answer(text, reply_markup=keyboard)


async def answer_callback(
    event: CallbackQuery, text: str | None = None, *, alert: bool = False
) -> None:
    """Acknowledge a callback query, ignoring expired-query errors."""
    try:
        await event.answer(text or None, show_alert=alert)
    except TelegramBadRequest:
        pass


def target_message(event: Message | CallbackQuery) -> Message | None:
    return event if isinstance(event, Message) else event.message
