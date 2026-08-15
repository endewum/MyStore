"""Fallback handlers for unmatched input.

Registered last: anything that reaches here is either stale callback data from
an old message or free text the bot has no flow for.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import NoopCB
from app.bot.handlers.helpers import answer_callback
from app.bot.keyboards.common import home_keyboard
from app.database.models import Admin, User
from app.services.registry import Services
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Router(name="fallback")


@router.callback_query(NoopCB.filter())
async def noop(callback: CallbackQuery) -> None:
    """Inert buttons such as the page indicator."""
    await answer_callback(callback)


@router.callback_query()
async def stale_callback(callback: CallbackQuery) -> None:
    logger.info(
        "callback.unhandled",
        data=callback.data,
        telegram_id=callback.from_user.id if callback.from_user else None,
    )
    await answer_callback(
        callback,
        "This button is no longer valid. Please open the menu again.",
        alert=True,
    )


@router.message(F.text)
async def unknown_text(
    message: Message,
    user: User,
    services: Services,
    admin: Admin | None = None,
) -> None:
    unread = await services.notifications.unread_count(user)
    pending = await services.orders.count_open_for_user(user)
    await message.answer(
        "🤔 I did not understand that.\n\nUse the menu below or send /start.",
        reply_markup=home_keyboard(
            unread=unread, pending_orders=pending, is_admin=admin is not None
        ),
    )


@router.message()
async def unknown_content(message: Message) -> None:
    await message.answer("🤔 Please use the menu buttons or send /start.")
