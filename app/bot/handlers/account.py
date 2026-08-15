"""Customer account screens."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AccountCB, MenuCB
from app.bot.handlers.helpers import render
from app.bot.keyboards.common import BTN_ACCOUNT
from app.bot.keyboards.orders import account_keyboard, stock_alerts_keyboard
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.registry import Services

router = Router(name="account")


async def _show_account(
    event: Message | CallbackQuery, user: User, services: Services
) -> None:
    stats = await services.users.user_stats(user)
    await render(
        event,
        texts.account(user.full_name, user.username, user.telegram_id, stats),
        account_keyboard(notifications_enabled=user.notifications_enabled),
    )


@router.message(Command("account"))
@router.message(F.text == BTN_ACCOUNT)
async def cmd_account(
    message: Message, state: FSMContext, user: User, services: Services
) -> None:
    await state.clear()
    await _show_account(message, user, services)


@router.callback_query(MenuCB.filter(F.action == "account"))
@router.callback_query(AccountCB.filter(F.action == "home"))
async def open_account(
    callback: CallbackQuery, state: FSMContext, user: User, services: Services
) -> None:
    await state.clear()
    await _show_account(callback, user, services)


@router.callback_query(AccountCB.filter(F.action == "toggle_notify"))
async def toggle_notifications(
    callback: CallbackQuery, user: User, services: Services
) -> None:
    enabled = await services.users.toggle_notifications(user)
    stats = await services.users.user_stats(user)
    await render(
        callback,
        texts.account(user.full_name, user.username, user.telegram_id, stats),
        account_keyboard(notifications_enabled=enabled),
        answer_text="🔔 Alerts enabled" if enabled else "🔕 Alerts disabled",
    )


@router.callback_query(AccountCB.filter(F.action == "alerts"))
async def open_alerts(
    callback: CallbackQuery,
    callback_data: AccountCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """The customer's own "Notify Me" waiting list."""
    result = await services.notifications.my_alerts(
        user, callback_data.page, settings.store.notifications_per_page
    )
    await render(callback, texts.stock_alerts(result), stock_alerts_keyboard(result))
