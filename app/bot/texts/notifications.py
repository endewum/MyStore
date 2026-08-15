"""Notification and broadcast message templates."""

from __future__ import annotations

from app.database.models import Order, Payment, Plan
from app.utils.text import DIVIDER, esc, money


def back_in_stock(plan: Plan, *, targeted: bool) -> str:
    """Restock announcement.

    ``targeted`` renders the personal variant sent to users who explicitly
    tapped 🔔 Notify Me; otherwise the public "back in stock" variant is used.
    """
    product = plan.product
    if targeted:
        head = "🔔 <b>Your requested product is back!</b>"
    else:
        head = f"{DIVIDER}\n🔥 <b>BACK IN STOCK</b>\n{DIVIDER}"
    lines = [
        head,
        "",
        f"{product.emoji} <b>{esc(product.name)}</b>",
        esc(plan.name),
        "",
        f"💵 {money(plan.price, plan.currency)}",
        f"📦 {plan.available_quantity} available",
    ]
    if plan.duration:
        lines.insert(4, f"⏳ {esc(plan.duration)}")
    lines += ["", "Limited stock available."]
    return "\n".join(lines)


def stock_notification_preview(plan: Plan, recipients: int, *, targeted: bool) -> str:
    return "\n".join(
        [
            f"{DIVIDER}\n👁 <b>PREVIEW</b>\n{DIVIDER}",
            "",
            back_in_stock(plan, targeted=targeted),
            "",
            DIVIDER,
            "",
            f"<b>Recipients</b>\n{recipients} user(s)",
            "",
            "Nothing has been sent yet.",
        ]
    )


def payment_confirmed(order: Order) -> str:
    return "\n".join(
        [
            f"{DIVIDER}\n✅ <b>PAYMENT CONFIRMED</b>\n{DIVIDER}",
            "",
            f"<b>Order #{esc(order.order_number)}</b>",
            "",
            "Your payment was verified by our team.",
            "We are preparing your order now — you will receive it shortly.",
        ]
    )


def payment_rejected(order: Order, payment: Payment) -> str:
    lines = [
        f"{DIVIDER}\n🚫 <b>PAYMENT REJECTED</b>\n{DIVIDER}",
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
        "",
        "We could not verify your payment.",
    ]
    if payment.rejection_reason:
        lines += ["", "<b>Reason</b>", esc(payment.rejection_reason)]
    lines += [
        "",
        "You can submit your payment details again, or contact support if you "
        "need help.",
    ]
    return "\n".join(lines)


def order_cancelled(order: Order, reason: str | None) -> str:
    lines = [
        f"{DIVIDER}\n❌ <b>ORDER CANCELLED</b>\n{DIVIDER}",
        "",
        f"<b>Order #{esc(order.order_number)}</b>",
    ]
    if reason:
        lines += ["", "<b>Reason</b>", esc(reason)]
    lines += ["", "The reserved stock has been released."]
    return "\n".join(lines)


def order_refunded(order: Order) -> str:
    return "\n".join(
        [
            f"{DIVIDER}\n↩️ <b>ORDER REFUNDED</b>\n{DIVIDER}",
            "",
            f"<b>Order #{esc(order.order_number)}</b>",
            "",
            f"A refund of {money(order.total, order.currency)} has been approved.",
            "Please contact support if you have any questions.",
        ]
    )


def new_payment_for_review(order: Order, payment: Payment, customer: str) -> str:
    """Alert pushed to administrators when a customer submits evidence."""
    item = order.item
    lines = [
        f"{DIVIDER}\n💰 <b>PAYMENT REVIEW</b>\n{DIVIDER}",
        "",
        f"<b>Order</b>\n#{esc(order.order_number)}",
        "",
        f"<b>Customer</b>\n{esc(customer)}",
        "",
        f"<b>Product</b>\n{esc(item.product_name if item else '—')}",
        "",
        f"<b>Plan</b>\n{esc(item.plan_name if item else '—')}",
        "",
        f"<b>Amount</b>\n{money(payment.amount, payment.currency)}",
        "",
        f"<b>Payment method</b>\n{esc(payment.method_name or '—')}",
    ]
    if payment.reference:
        lines += ["", f"<b>Transaction reference</b>\n<code>{esc(payment.reference)}</code>"]
    if payment.proof_file_id:
        lines += ["", "📸 Screenshot attached"]
    return "\n".join(lines)


def fulfillment_required(order: Order, customer: str) -> str:
    item = order.item
    return "\n".join(
        [
            f"{DIVIDER}\n📦 <b>FULFILLMENT REQUIRED</b>\n{DIVIDER}",
            "",
            f"<b>Order</b>\n#{esc(order.order_number)}",
            "",
            f"<b>Customer</b>\n{esc(customer)}",
            "",
            f"<b>Product</b>\n{esc(item.product_name if item else '—')}",
            "",
            f"<b>Plan</b>\n{esc(item.plan_name if item else '—')}",
            "",
            "<b>Payment</b>\n✅ Confirmed",
        ]
    )
