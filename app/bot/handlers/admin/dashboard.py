"""Admin panel entry point and dashboard."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminCB, MenuCB
from app.bot.filters import AdminOnly, IsAdmin
from app.bot.handlers.helpers import render
from app.bot.keyboards.admin.menu import admin_menu_keyboard, dashboard_keyboard
from app.bot.texts import admin as texts
from app.database.models import Admin
from app.services.registry import Services

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


@router.message(Command("admin"), AdminOnly())
async def cmd_admin(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    await state.clear()
    await _show_panel(message, admin, services)


@router.callback_query(MenuCB.filter(F.action == "admin"), AdminOnly())
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
