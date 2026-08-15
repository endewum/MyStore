"""Customer notification inbox."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuCB, NotifyCB
from app.bot.handlers.helpers import render
from app.bot.keyboards.common import BTN_NOTIFICATIONS
from app.bot.keyboards.orders import notifications_keyboard
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.registry import Services

router = Router(name="notifications")


async def _show_inbox(
    event: Message | CallbackQuery,
    user: User,
    services: Services,
    settings: Settings,
    page: int = 1,
) -> None:
    result = await services.notifications.inbox(
        user, page, settings.store.notifications_per_page
    )
    unread = await services.notifications.unread_count(user)
    await render(
        event,
        texts.notifications(result, unread=unread),
        notifications_keyboard(result, unread=unread),
    )


@router.message(Command("notifications"))
@router.message(F.text == BTN_NOTIFICATIONS)
async def cmd_notifications(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_inbox(message, user, services, settings)


@router.callback_query(MenuCB.filter(F.action == "notifications"))
async def open_notifications(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_inbox(callback, user, services, settings)


@router.callback_query(NotifyCB.filter(F.action == "list"))
async def paginate_notifications(
    callback: CallbackQuery,
    callback_data: NotifyCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await _show_inbox(callback, user, services, settings, callback_data.page)


@router.callback_query(NotifyCB.filter(F.action == "read_all"))
async def mark_all_read(
    callback: CallbackQuery,
    callback_data: NotifyCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await services.notifications.mark_all_read(user)
    result = await services.notifications.inbox(
        user, callback_data.page, settings.store.notifications_per_page
    )
    await render(
        callback,
        texts.notifications(result, unread=0),
        notifications_keyboard(result, unread=0),
        answer_text="✅ All notifications marked as read.",
    )
