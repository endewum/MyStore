"""Admin panel menu keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AdminBroadcastCB,
    AdminCB,
    AdminOrderCB,
    AdminPaymentCB,
    AdminProductCB,
    AdminSettingCB,
    AdminStockCB,
    AdminUserCB,
    MenuCB,
)
from app.bot.keyboards.common import back_home_row


def admin_menu_keyboard(
    *, pending_payments: int = 0, awaiting_fulfilment: int = 0
) -> InlineKeyboardMarkup:
    """Main admin panel with badges for work that needs attention."""
    payments_label = "💳 Payments"
    if pending_payments:
        payments_label = f"💳 Payments ({pending_payments})"
    orders_label = "🧾 Orders"
    if awaiting_fulfilment:
        orders_label = f"🧾 Orders ({awaiting_fulfilment})"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📊 Dashboard", callback_data=AdminCB(section="dashboard").pack()
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🛍 Products",
            callback_data=AdminProductCB(action="list", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="📦 Inventory",
            callback_data=AdminStockCB(action="low", page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=orders_label,
            callback_data=AdminOrderCB(action="list", page=1, value="open").pack(),
        ),
        InlineKeyboardButton(
            text=payments_label,
            callback_data=AdminPaymentCB(action="queue", page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👥 Users", callback_data=AdminUserCB(action="list", page=1).pack()
        ),
        InlineKeyboardButton(
            text="📢 Broadcast",
            callback_data=AdminBroadcastCB(action="menu").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🎟 Coupons",
            callback_data=AdminSettingCB(action="coupons", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="⚙️ Settings", callback_data=AdminSettingCB(action="menu").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="💳 Payment methods",
            callback_data=AdminPaymentCB(action="methods").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏠 Customer view", callback_data=MenuCB(action="home").pack()
        )
    )
    return builder.as_markup()


def dashboard_keyboard(*, pending_payments: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pending_payments:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Review {pending_payments} payment(s)",
                callback_data=AdminPaymentCB(action="queue", page=1).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="📦 Sold-out plans",
            callback_data=AdminStockCB(action="low", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="🧾 Open orders",
            callback_data=AdminOrderCB(action="list", page=1, value="open").pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📜 Audit log",
            callback_data=AdminSettingCB(action="logs", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 Refresh", callback_data=AdminCB(section="dashboard").pack()
        ),
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def admin_back_keyboard(section: str = "home") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*back_home_row(AdminCB(section=section).pack()))
    return builder.as_markup()
