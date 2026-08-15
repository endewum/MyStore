"""Home screen, help and support handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import MenuCB
from app.bot.handlers.helpers import render
from app.bot.keyboards.common import (
    BTN_HELP,
    BTN_SUPPORT,
    home_keyboard,
    main_reply_keyboard,
    navigation_keyboard,
)
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import Admin, User
from app.services.registry import Services

router = Router(name="start")


async def _home_screen(
    event: Message | CallbackQuery,
    user: User,
    services: Services,
    settings: Settings,
    admin: Admin | None,
) -> None:
    unread = await services.notifications.unread_count(user)
    pending = await services.orders.count_open_for_user(user)
    welcome = await services.store_settings.get("store_welcome")
    await render(
        event,
        texts.home(settings.store.name, welcome, first_name=user.first_name),
        home_keyboard(
            unread=unread, pending_orders=pending, is_admin=admin is not None
        ),
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
    admin: Admin | None = None,
) -> None:
    """Entry point: reset any in-progress flow and show the home screen."""
    await state.clear()
    await message.answer(
        f"🏪 <b>{settings.store.name}</b>\nUse the menu below at any time.",
        reply_markup=main_reply_keyboard(),
    )
    if admin is not None:
        # The configured administrator lands in management immediately, while
        # the persistent customer menu remains available for customer testing.
        from app.bot.keyboards.admin.menu import admin_menu_keyboard
        from app.bot.texts import admin as admin_texts

        counts = await services.dashboard.counts()
        await message.answer(
            admin_texts.panel(admin, counts),
            reply_markup=admin_menu_keyboard(
                pending_payments=counts["pending_payments"],
                awaiting_fulfilment=counts["awaiting_fulfilment"],
            ),
        )
        return
    await _home_screen(message, user, services, settings, admin)


@router.callback_query(MenuCB.filter(F.action == "home"))
async def open_home(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
    admin: Admin | None = None,
) -> None:
    await state.clear()
    await _home_screen(callback, user, services, settings, admin)


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, services: Services) -> None:
    body = await services.store_settings.get("help_text")
    await render(
        message,
        texts.help_text(body),
        navigation_keyboard(MenuCB(action="home").pack()),
    )


@router.callback_query(MenuCB.filter(F.action == "help"))
async def open_help(callback: CallbackQuery, services: Services) -> None:
    body = await services.store_settings.get("help_text")
    await render(
        callback,
        texts.help_text(body),
        navigation_keyboard(MenuCB(action="home").pack()),
    )


async def _support_screen(
    event: Message | CallbackQuery, services: Services, settings: Settings
) -> None:
    username = await services.store_settings.get("support_username")
    body = await services.store_settings.get("support_text")
    await render(
        event,
        texts.support(username or settings.store.support_username, body),
        navigation_keyboard(MenuCB(action="home").pack()),
    )


@router.message(Command("support"))
@router.message(F.text == BTN_SUPPORT)
async def cmd_support(
    message: Message, services: Services, settings: Settings
) -> None:
    await _support_screen(message, services, settings)


@router.callback_query(MenuCB.filter(F.action == "support"))
async def open_support(
    callback: CallbackQuery, services: Services, settings: Settings
) -> None:
    await _support_screen(callback, services, settings)


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
    admin: Admin | None = None,
) -> None:
    """Escape hatch out of any FSM flow."""
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("❌ Cancelled.")
    await _home_screen(message, user, services, settings, admin)
