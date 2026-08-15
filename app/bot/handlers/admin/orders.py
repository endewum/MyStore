"""Admin order management and manual fulfilment."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminOrderCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.orders import (
    FILTER_MAP,
    order_detail_keyboard,
    orders_keyboard,
)
from app.bot.keyboards.common import navigation_keyboard
from app.bot.keyboards.orders import order_delivered_keyboard
from app.bot.states import OrderStates
from app.bot.texts import admin as texts
from app.bot.texts import customer as customer_texts
from app.bot.texts import notifications as notify_texts
from app.config import Settings
from app.database.models import Admin, NotificationType, Order
from app.services.registry import Services
from app.utils.logging import get_logger
from app.utils.text import clean_multiline

logger = get_logger(__name__)

router = Router(name="admin-orders")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

#: Sentinel the admin can send to deliver the reserved inventory as-is.
USE_RESERVED_COMMAND = "/use"


async def _show_orders(
    event: Message | CallbackQuery,
    services: Services,
    settings: Settings,
    *,
    page: int,
    filter_key: str,
) -> None:
    label, statuses = FILTER_MAP.get(filter_key, FILTER_MAP["open"])
    result = await services.orders.paginate_admin(
        list(statuses) or None, page, settings.store.admin_list_page_size
    )
    await render(
        event,
        texts.orders_list(result, label),
        orders_keyboard(result, active_filter=filter_key),
    )


async def _show_order(
    event: Message | CallbackQuery,
    services: Services,
    order_id: int,
    *,
    page: int = 1,
    filter_key: str = "open",
) -> None:
    order = await services.orders.get(order_id)
    payment = await services.payments.latest_for_order(order.id)
    user = await services.users.get_by_id(order.user_id)
    await render(
        event,
        texts.order_detail(order, user, payment),
        order_detail_keyboard(
            order, page=page, active_filter=filter_key, payment=payment
        ),
    )


@router.callback_query(AdminOrderCB.filter(F.action == "list"))
async def list_orders(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_orders(
        callback,
        services,
        settings,
        page=callback_data.page,
        filter_key=callback_data.value or "open",
    )


@router.callback_query(AdminOrderCB.filter(F.action == "view"))
async def view_order(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_order(
        callback,
        services,
        callback_data.order_id,
        page=callback_data.page,
        filter_key=callback_data.value or "open",
    )


@router.callback_query(AdminOrderCB.filter(F.action == "history"))
async def order_history(
    callback: CallbackQuery, callback_data: AdminOrderCB, services: Services
) -> None:
    order = await services.orders.get(callback_data.order_id)
    history = await services.orders.history_for_order(order.id)
    await render(
        callback,
        texts.order_history(order, history),  # type: ignore[arg-type]
        navigation_keyboard(
            AdminOrderCB(
                action="view",
                order_id=order.id,
                page=callback_data.page,
                value=callback_data.value or "open",
            ).pack()
        ),
    )


@router.callback_query(AdminOrderCB.filter(F.action == "process"))
async def mark_processing(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    admin: Admin,
    services: Services,
) -> None:
    order = await services.orders.get(callback_data.order_id)
    await services.orders.start_processing(order, admin)
    await _show_order(
        callback,
        services,
        order.id,
        page=callback_data.page,
        filter_key=callback_data.value or "open",
    )


# --------------------------------------------------------------------- fulfilment
@router.callback_query(AdminOrderCB.filter(F.action == "fulfill"))
async def ask_delivery(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    state: FSMContext,
    services: Services,
) -> None:
    """Prompt for the delivery payload, pre-filling reserved inventory."""
    order = await services.orders.get(callback_data.order_id)
    suggestion = await services.orders.auto_delivery_preview(order)
    await state.set_state(OrderStates.waiting_delivery_content)
    await state.update_data(
        order_id=order.id,
        page=callback_data.page,
        filter_key=callback_data.value or "open",
        suggestion=suggestion,
    )
    await render(
        callback,
        texts.fulfillment_prompt(order, suggestion),
        navigation_keyboard(
            AdminOrderCB(
                action="view",
                order_id=order.id,
                page=callback_data.page,
                value=callback_data.value or "open",
            ).pack()
        ),
    )


@router.message(OrderStates.waiting_delivery_content, F.text)
async def deliver_order(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    order = await services.orders.get(int(data["order_id"]))
    raw = (message.text or "").strip()
    suggestion = data.get("suggestion")

    if raw == USE_RESERVED_COMMAND:
        if not suggestion:
            await message.answer(
                "⚠️ This order has no reserved inventory. Send the delivery "
                "details manually."
            )
            return
        content = str(suggestion)
    else:
        try:
            content = clean_multiline(raw, max_length=3000, field="delivery details")
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return

    order = await services.orders.fulfill(order, admin, content)
    await state.clear()
    await message.answer(
        f"✅ Order #{order.order_number} delivered.\n"
        "The customer has been notified."
    )
    await _notify_customer_delivered(services, order)
    await _show_order(
        message,
        services,
        order.id,
        page=int(data.get("page", 1)),
        filter_key=str(data.get("filter_key", "open")),
    )


async def _notify_customer_delivered(services: Services, order: Order) -> None:
    user = await services.users.get_by_id(order.user_id)
    if user is None:
        return
    await services.notifications.notify_user(
        user,
        type=NotificationType.ORDER_UPDATE,
        title=f"Order #{order.order_number} completed",
        body="Your order has been fulfilled. Open it to see your delivery.",
        message_text=customer_texts.order_delivered(order),
        reply_markup=order_delivered_keyboard(),
        order_id=order.id,
    )


# ------------------------------------------------------------- cancel / refund
@router.callback_query(AdminOrderCB.filter(F.action.in_({"cancel", "refund"})))
async def ask_reason(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    state: FSMContext,
    services: Services,
) -> None:
    order = await services.orders.get(callback_data.order_id)
    mode = callback_data.action
    await state.set_state(OrderStates.waiting_cancel_reason)
    await state.update_data(
        order_id=order.id,
        mode=mode,
        page=callback_data.page,
        filter_key=callback_data.value or "open",
    )
    verb = "cancel" if mode == "cancel" else "refund"
    await render(
        callback,
        f"✍️ Send a short reason to {verb} order <b>#{order.order_number}</b>.\n\n"
        "Send <code>-</code> to skip the reason.",
        navigation_keyboard(
            AdminOrderCB(
                action="view",
                order_id=order.id,
                page=callback_data.page,
                value=callback_data.value or "open",
            ).pack()
        ),
    )


@router.message(OrderStates.waiting_cancel_reason, F.text)
async def apply_cancel(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    order = await services.orders.get(int(data["order_id"]))
    raw = (message.text or "").strip()
    reason = None if raw == "-" else raw[:255]

    if str(data["mode"]) == "cancel":
        order = await services.orders.cancel_by_admin(order, admin, reason)
        text = notify_texts.order_cancelled(order, reason)
        title = f"Order #{order.order_number} cancelled"
    else:
        order = await services.orders.refund(order, admin, reason)
        text = notify_texts.order_refunded(order)
        title = f"Order #{order.order_number} refunded"

    await state.clear()
    user = await services.users.get_by_id(order.user_id)
    if user is not None:
        await services.notifications.notify_user(
            user,
            type=NotificationType.ORDER_UPDATE,
            title=title,
            body=reason or "See your order for details.",
            message_text=text,
            order_id=order.id,
        )
    await message.answer(f"✅ {title}. The customer has been notified.")
    await _show_order(
        message,
        services,
        order.id,
        page=int(data.get("page", 1)),
        filter_key=str(data.get("filter_key", "open")),
    )


@router.callback_query(AdminOrderCB.filter(F.action == "user"))
async def orders_for_user(
    callback: CallbackQuery,
    callback_data: AdminOrderCB,
    services: Services,
    settings: Settings,
) -> None:
    """Order history of one customer (``order_id`` carries the user id here)."""
    user = await services.users.get_by_id(callback_data.order_id)
    if user is None:
        await answer_callback(callback, "User not found.", alert=True)
        return
    result = await services.orders.paginate_for_user(
        user, callback_data.page, settings.store.admin_list_page_size
    )
    await render(
        callback,
        texts.orders_list(result, f"Orders of {user.display_name}"),
        orders_keyboard(result, active_filter="all"),
    )
