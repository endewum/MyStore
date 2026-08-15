"""Admin keyboards for orders, payment review and payment methods."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB, AdminOrderCB, AdminPaymentCB, AdminUserCB
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Order, OrderStatus, Payment, PaymentMethod
from app.utils.pagination import Page
from app.utils.text import truncate

#: Named order filters offered on the admin order list.
ORDER_FILTERS: tuple[tuple[str, str, tuple[OrderStatus, ...]], ...] = (
    (
        "open",
        "🔥 Needs action",
        (
            OrderStatus.PAYMENT_SUBMITTED,
            OrderStatus.PAID,
            OrderStatus.PROCESSING,
            OrderStatus.READY,
        ),
    ),
    ("review", "🔎 Payment review", (OrderStatus.PAYMENT_SUBMITTED,)),
    (
        "fulfil",
        "📦 To fulfil",
        (OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.READY),
    ),
    ("pending", "⏳ Awaiting payment", (OrderStatus.PENDING_PAYMENT,)),
    ("done", "✅ Delivered", (OrderStatus.DELIVERED,)),
    (
        "closed",
        "❌ Cancelled / refunded",
        (OrderStatus.CANCELLED, OrderStatus.REFUNDED, OrderStatus.PAYMENT_REJECTED),
    ),
    ("all", "🗂 All orders", ()),
)

FILTER_MAP = {key: (label, statuses) for key, label, statuses in ORDER_FILTERS}


def orders_keyboard(page: Page[Order], *, active_filter: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in page.items:
        item = order.item
        builder.row(
            InlineKeyboardButton(
                text=truncate(
                    f"{order.status.label.split(' ')[0]} #{order.order_number} · "
                    f"{item.product_name if item else '—'} · {order.total_display}",
                    36,
                ),
                callback_data=AdminOrderCB(
                    action="view",
                    order_id=order.id,
                    page=page.page,
                    value=active_filter,
                ).pack(),
            )
        )
    nav = pagination_row(
        page,
        lambda target: AdminOrderCB(
            action="list", page=target, value=active_filter
        ).pack(),
    )
    if nav:
        builder.row(*nav)

    filters = [
        InlineKeyboardButton(
            text=label,
            callback_data=AdminOrderCB(action="list", page=1, value=key).pack(),
        )
        for key, label, _ in ORDER_FILTERS
        if key != active_filter
    ]
    for index in range(0, len(filters), 2):
        builder.row(*filters[index : index + 2])
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def order_detail_keyboard(
    order: Order,
    *,
    page: int = 1,
    active_filter: str = "open",
    payment: Payment | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if order.status is OrderStatus.PAYMENT_SUBMITTED and payment is not None:
        builder.row(
            InlineKeyboardButton(
                text="💰 Review payment",
                callback_data=AdminPaymentCB(
                    action="view", payment_id=payment.id, page=1
                ).pack(),
            )
        )
    if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.READY}:
        builder.row(
            InlineKeyboardButton(
                text="📦 Fulfill order",
                callback_data=AdminOrderCB(
                    action="fulfill", order_id=order.id, page=page, value=active_filter
                ).pack(),
            )
        )
    if order.status is OrderStatus.PAID:
        builder.row(
            InlineKeyboardButton(
                text="⚙️ Mark processing",
                callback_data=AdminOrderCB(
                    action="process", order_id=order.id, page=page, value=active_filter
                ).pack(),
            )
        )
    if payment is not None and payment.proof_file_id:
        builder.row(
            InlineKeyboardButton(
                text="🖼 View payment proof",
                callback_data=AdminPaymentCB(
                    action="proof", payment_id=payment.id
                ).pack(),
            )
        )
    if not order.status.is_final:
        builder.row(
            InlineKeyboardButton(
                text="❌ Cancel order",
                callback_data=AdminOrderCB(
                    action="cancel", order_id=order.id, page=page, value=active_filter
                ).pack(),
            )
        )
    if order.status is OrderStatus.DELIVERED:
        builder.row(
            InlineKeyboardButton(
                text="↩️ Refund order",
                callback_data=AdminOrderCB(
                    action="refund", order_id=order.id, page=page, value=active_filter
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🕘 Status history",
            callback_data=AdminOrderCB(
                action="history", order_id=order.id, page=page, value=active_filter
            ).pack(),
        ),
        InlineKeyboardButton(
            text="👤 Customer",
            callback_data=AdminUserCB(action="view", user_id=order.user_id).pack(),
        ),
    )
    builder.row(
        *back_home_row(
            AdminOrderCB(action="list", page=page, value=active_filter).pack()
        )
    )
    return builder.as_markup()


def payment_queue_keyboard(page: Page[Payment]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for payment in page.items:
        order = payment.order
        builder.row(
            InlineKeyboardButton(
                text=truncate(
                    f"💰 #{order.order_number if order else '?'} · "
                    f"{payment.amount_display} · {payment.method_name or '—'}",
                    36,
                ),
                callback_data=AdminPaymentCB(
                    action="view", payment_id=payment.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminPaymentCB(action="queue", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="💳 Payment methods",
            callback_data=AdminPaymentCB(action="methods").pack(),
        )
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def payment_review_keyboard(payment: Payment, *, page: int = 1) -> InlineKeyboardMarkup:
    """Confirm / reject buttons for a manually submitted payment."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Confirm Payment",
            callback_data=AdminPaymentCB(
                action="confirm", payment_id=payment.id, page=page
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Reject Payment",
            callback_data=AdminPaymentCB(
                action="reject", payment_id=payment.id, page=page
            ).pack(),
        )
    )
    if payment.proof_file_id:
        builder.row(
            InlineKeyboardButton(
                text="🖼 View proof",
                callback_data=AdminPaymentCB(
                    action="proof", payment_id=payment.id, page=page
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔎 View order",
            callback_data=AdminOrderCB(
                action="view", order_id=payment.order_id, page=1, value="open"
            ).pack(),
        )
    )
    builder.row(*back_home_row(AdminPaymentCB(action="queue", page=page).pack()))
    return builder.as_markup()


def payment_methods_keyboard(methods: Sequence[PaymentMethod]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for method in methods:
        state = "🟢" if method.is_enabled and method.is_configured else "⚫"
        builder.row(
            InlineKeyboardButton(
                text=f"{state} {method.button_title}",
                callback_data=AdminPaymentCB(
                    action="method", method_id=method.id
                ).pack(),
            )
        )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def payment_method_keyboard(method: PaymentMethod) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    fields = [
        InlineKeyboardButton(
            text=label,
            callback_data=AdminPaymentCB(
                action="field", method_id=method.id, value=field
            ).pack(),
        )
        for field, label in (
            ("account_identifier", "🔑 Account / wallet"),
            ("network", "🌐 Network"),
            ("instructions", "📝 Instructions"),
            ("name", "✏️ Display name"),
            ("emoji", "😀 Emoji"),
            ("min_amount", "💵 Minimum amount"),
        )
    ]
    for index in range(0, len(fields), 2):
        builder.row(*fields[index : index + 2])
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if method.is_enabled else "🟢 Enable",
            callback_data=AdminPaymentCB(
                action="toggle", method_id=method.id
            ).pack(),
        ),
        InlineKeyboardButton(
            text=(
                "🖼 Screenshot: required"
                if method.requires_screenshot
                else "🖼 Screenshot: optional"
            ),
            callback_data=AdminPaymentCB(
                action="toggle_proof", method_id=method.id
            ).pack(),
        ),
    )
    builder.row(*back_home_row(AdminPaymentCB(action="methods").pack()))
    return builder.as_markup()
