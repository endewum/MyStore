"""Customer order history and order detail."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import ConfirmCB, MenuCB, OrderCB
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.common import BTN_ORDERS, confirm_keyboard
from app.bot.keyboards.orders import order_detail_keyboard, orders_list_keyboard
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.registry import Services

router = Router(name="orders")

CANCEL_SCOPE = "order_cancel"


async def _show_orders(
    event: Message | CallbackQuery,
    user: User,
    services: Services,
    settings: Settings,
    page: int = 1,
) -> None:
    result = await services.orders.paginate_for_user(
        user, page, settings.store.orders_per_page
    )
    await render(event, texts.orders_list(result), orders_list_keyboard(result))


@router.message(Command("orders"))
@router.message(F.text == BTN_ORDERS)
async def cmd_orders(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_orders(message, user, services, settings)


@router.callback_query(MenuCB.filter(F.action == "orders"))
async def open_orders(
    callback: CallbackQuery,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_orders(callback, user, services, settings)


@router.callback_query(OrderCB.filter(F.action == "list"))
async def paginate_orders(
    callback: CallbackQuery,
    callback_data: OrderCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    await _show_orders(callback, user, services, settings, callback_data.page)


@router.callback_query(OrderCB.filter(F.action == "view"))
async def view_order(
    callback: CallbackQuery,
    callback_data: OrderCB,
    user: User,
    services: Services,
) -> None:
    """Order detail. Ownership is enforced by the service layer."""
    order = await services.orders.get_for_user(callback_data.order_id, user)
    payment = await services.payments.latest_for_order(order.id)
    await render(
        callback,
        texts.order_detail(order, payment=payment),
        order_detail_keyboard(order, page=callback_data.page),
    )


@router.callback_query(OrderCB.filter(F.action == "cancel"))
async def ask_cancel(
    callback: CallbackQuery,
    callback_data: OrderCB,
    user: User,
    services: Services,
) -> None:
    order = await services.orders.get_for_user(callback_data.order_id, user)
    await render(
        callback,
        f"❓ Cancel order <b>#{order.order_number}</b>?\n\n"
        "The reserved stock will be released and the order closed.",
        confirm_keyboard(
            CANCEL_SCOPE,
            order.id,
            confirm_text="✅ Yes, cancel it",
            cancel_text="◀️ Keep the order",
        ),
    )


@router.callback_query(ConfirmCB.filter(F.scope == CANCEL_SCOPE))
async def confirm_cancel(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    user: User,
    services: Services,
) -> None:
    order = await services.orders.get_for_user(callback_data.target_id, user)
    if callback_data.action == "yes":
        await services.orders.cancel_by_customer(order, user)
        await answer_callback(callback, "Order cancelled.")
    payment = await services.payments.latest_for_order(order.id)
    await render(
        callback, texts.order_detail(order, payment=payment), order_detail_keyboard(order)
    )
