"""Admin panel entry point and dashboard."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminCB, MenuCB
from app.bot.filters import IsAdmin, has_access
from app.bot.filters.admin import DENIED
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.menu import admin_menu_keyboard, dashboard_keyboard
from app.bot.texts import admin as texts
from app.database.models import Admin, AdminRole
from app.services.registry import Services
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Router(name="admin-dashboard")


async def _show_panel(
    event: Message | CallbackQuery, admin: Admin, services: Services
) -> None:
    counts = await services.dashboard.counts()
    await render(
        event,
        texts.panel(admin, counts),
        admin_menu_keyboard(
            pending_payments=counts["pending_payments"],
            awaiting_fulfilment=counts["awaiting_fulfilment"],
        ),
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    state: FSMContext,
    services: Services,
    admin: Admin | None = None,
) -> None:
    """Entry point. Authorization is checked here so an unauthorized user gets
    exactly one clear answer instead of falling through to the fallback."""
    if not has_access(admin, AdminRole.STAFF):
        logger.warning("admin.access_denied", telegram_id=message.from_user.id)
        await message.answer(DENIED)
        return
    await state.clear()
    await _show_panel(message, admin, services)


@router.callback_query(MenuCB.filter(F.action == "admin"))
async def open_panel_from_menu(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    admin: Admin | None = None,
) -> None:
    if not has_access(admin, AdminRole.STAFF):
        logger.warning("admin.access_denied", telegram_id=callback.from_user.id)
        await answer_callback(callback, DENIED, alert=True)
        return
    await state.clear()
    await _show_panel(callback, admin, services)


@router.callback_query(AdminCB.filter(F.section == "home"), IsAdmin())
async def open_panel(
    callback: CallbackQuery, state: FSMContext, admin: Admin, services: Services
) -> None:
    await state.clear()
    await _show_panel(callback, admin, services)


@router.callback_query(AdminCB.filter(F.section == "dashboard"), IsAdmin())
async def open_dashboard(callback: CallbackQuery, services: Services) -> None:
    stats = await services.dashboard.stats()
    await render(
        callback,
        texts.dashboard(stats),
        dashboard_keyboard(pending_payments=stats.pending_payments),
    )
