"""Order, payment and account keyboards."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AccountCB,
    MenuCB,
    NotifyCB,
    OrderCB,
    PayCB,
    PlanCB,
    ProductCB,
    StoreCB,
)
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Order, OrderStatus, PaymentMethod, StockAlert
from app.utils.pagination import Page
from app.utils.text import truncate

#: Statuses in which the customer can still act on the order.
_PAYABLE = {OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_REJECTED}


def orders_list_keyboard(page: Page[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in page.items:
        item = order.item
        title = truncate(
            f"#{order.order_number} · {item.product_name if item else '—'}", 30
        )
        builder.row(
            InlineKeyboardButton(
                text=f"{order.status.label.split(' ')[0]} {title}",
                callback_data=OrderCB(
                    action="view", order_id=order.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(page, lambda target: OrderCB(action="list", page=target).pack())
    if nav:
        builder.row(*nav)
    builder.row(*back_home_row(MenuCB(action="home").pack(), home=False))
    return builder.as_markup()


def order_detail_keyboard(order: Order, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if order.status in _PAYABLE:
        builder.row(
            InlineKeyboardButton(
                text="💳 Pay now",
                callback_data=PayCB(action="choose", order_id=order.id).pack(),
            )
        )
    if order.status is OrderStatus.PENDING_PAYMENT:
        builder.row(
            InlineKeyboardButton(
                text="❌ Cancel order",
                callback_data=OrderCB(
                    action="cancel", order_id=order.id, page=page
                ).pack(),
            )
        )
    item = order.item
    if item and item.product_id:
        builder.row(
            InlineKeyboardButton(
                text="🔁 Buy again",
                callback_data=ProductCB(product_id=item.product_id, page=1).pack(),
            )
        )
    builder.row(*back_home_row(OrderCB(action="list", page=page).pack()))
    return builder.as_markup()


def payment_methods_keyboard(
    order: Order, methods: Sequence[PaymentMethod]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for method in methods:
        builder.row(
            InlineKeyboardButton(
                text=method.button_title,
                callback_data=PayCB(
                    action="method", order_id=order.id, method_id=method.id
                ).pack(),
            )
        )
    builder.row(
        *back_home_row(OrderCB(action="view", order_id=order.id, page=1).pack())
    )
    return builder.as_markup()


def payment_instructions_keyboard(
    order: Order, method: PaymentMethod
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ I Have Paid",
            callback_data=PayCB(
                action="paid", order_id=order.id, method_id=method.id
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Change method",
            callback_data=PayCB(action="choose", order_id=order.id).pack(),
        )
    )
    builder.row(
        *back_home_row(OrderCB(action="view", order_id=order.id, page=1).pack())
    )
    return builder.as_markup()


def payment_submitting_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Shown while the bot waits for the customer's transaction details."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel submission",
            callback_data=PayCB(action="cancel", order_id=order.id).pack(),
        )
    )
    return builder.as_markup()


def order_submitted_keyboard(order: Order) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📦 View order",
            callback_data=OrderCB(action="view", order_id=order.id, page=1).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏪 Continue shopping",
            callback_data=StoreCB(page=1, category=0).pack(),
        )
    )
    return builder.as_markup()


def order_delivered_keyboard() -> InlineKeyboardMarkup:
    """Footer of the "order completed" message sent to the customer."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📦 My Orders", callback_data=OrderCB(action="list", page=1).pack()
        ),
        InlineKeyboardButton(text="🏠 Home", callback_data=MenuCB(action="home").pack()),
    )
    return builder.as_markup()


def account_keyboard(*, notifications_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📦 Orders", callback_data=OrderCB(action="list", page=1).pack()
        ),
        InlineKeyboardButton(
            text="🔔 Notifications", callback_data=NotifyCB(action="list", page=1).pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔖 My waiting list",
            callback_data=AccountCB(action="alerts", page=1).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=(
                "🔔 Alerts: ON" if notifications_enabled else "🔕 Alerts: OFF"
            ),
            callback_data=AccountCB(action="toggle_notify").pack(),
        )
    )
    builder.row(*back_home_row(MenuCB(action="home").pack(), home=False))
    return builder.as_markup()


def notifications_keyboard(page: Page[object], *, unread: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = pagination_row(page, lambda target: NotifyCB(action="list", page=target).pack())
    if nav:
        builder.row(*nav)
    if unread:
        builder.row(
            InlineKeyboardButton(
                text="✅ Mark all as read",
                callback_data=NotifyCB(action="read_all", page=page.page).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔖 My waiting list",
            callback_data=AccountCB(action="alerts", page=1).pack(),
        )
    )
    builder.row(*back_home_row(MenuCB(action="home").pack(), home=False))
    return builder.as_markup()


def stock_alerts_keyboard(page: Page[StockAlert]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for alert in page.items:
        plan = alert.plan
        if plan is None:
            continue
        builder.row(
            InlineKeyboardButton(
                text=f"🔕 Stop · {truncate(plan.name, 24)}",
                callback_data=PlanCB(action="unnotify", plan_id=plan.id, page=1).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AccountCB(action="alerts", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(*back_home_row(AccountCB(action="home").pack()))
    return builder.as_markup()
