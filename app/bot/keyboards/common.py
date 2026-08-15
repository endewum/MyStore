"""Shared keyboard building blocks."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import ConfirmCB, MenuCB, NoopCB
from app.utils.pagination import Page

#: Labels of the persistent reply keyboard, also used by message handlers.
BTN_STORE = "🏪 Store"
BTN_ORDERS = "📦 My Orders"
BTN_NOTIFICATIONS = "🔔 Notifications"
BTN_ACCOUNT = "👤 My Account"
BTN_SUPPORT = "📞 Support"
BTN_HELP = "ℹ️ Help"
BTN_SEARCH = "🔎 Search"

BACK_TEXT = "◀️ Back"
HOME_TEXT = "🏠 Home"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard with the six main sections."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STORE), KeyboardButton(text=BTN_ORDERS)],
            [KeyboardButton(text=BTN_SEARCH), KeyboardButton(text=BTN_NOTIFICATIONS)],
            [KeyboardButton(text=BTN_ACCOUNT), KeyboardButton(text=BTN_SUPPORT)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option…",
    )


def home_keyboard(
    *, unread: int = 0, pending_orders: int = 0, is_admin: bool = False
) -> InlineKeyboardMarkup:
    """Inline home menu with live badges."""
    builder = InlineKeyboardBuilder()
    builder.button(text=BTN_STORE, callback_data=MenuCB(action="store").pack())
    builder.button(text=BTN_SEARCH, callback_data=MenuCB(action="search").pack())

    orders_label = BTN_ORDERS if not pending_orders else f"{BTN_ORDERS} ({pending_orders})"
    notif_label = BTN_NOTIFICATIONS if not unread else f"{BTN_NOTIFICATIONS} ({unread})"
    builder.button(text=orders_label, callback_data=MenuCB(action="orders").pack())
    builder.button(text=notif_label, callback_data=MenuCB(action="notifications").pack())

    builder.button(text=BTN_ACCOUNT, callback_data=MenuCB(action="account").pack())
    builder.button(text=BTN_SUPPORT, callback_data=MenuCB(action="support").pack())
    builder.button(text=BTN_HELP, callback_data=MenuCB(action="help").pack())
    builder.adjust(2, 2, 2, 1)
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text="⚙️ Admin Panel", callback_data=MenuCB(action="admin").pack()
            )
        )
    return builder.as_markup()


def pagination_row(
    page: Page[object] | None,
    callback_for_page: Callable[[int], str],
    *,
    label: str | None = None,
) -> list[InlineKeyboardButton]:
    """Build a ``◀️ / n/m / ▶️`` row, or an empty row for single-page lists."""
    if page is None or page.total_pages <= 1:
        return []
    buttons: list[InlineKeyboardButton] = []
    if page.has_previous:
        buttons.append(
            InlineKeyboardButton(
                text="◀️ Previous", callback_data=callback_for_page(page.page - 1)
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text=label or f"📄 {page.label}",
            callback_data=NoopCB(tag="page").pack(),
        )
    )
    if page.has_next:
        buttons.append(
            InlineKeyboardButton(
                text="Next ➡️", callback_data=callback_for_page(page.page + 1)
            )
        )
    return buttons


def back_home_row(
    back_callback: str | None = None,
    *,
    back_text: str = BACK_TEXT,
    home: bool = True,
) -> list[InlineKeyboardButton]:
    """Standard navigation footer used on every screen."""
    row: list[InlineKeyboardButton] = []
    if back_callback:
        row.append(InlineKeyboardButton(text=back_text, callback_data=back_callback))
    if home:
        row.append(
            InlineKeyboardButton(
                text=HOME_TEXT, callback_data=MenuCB(action="home").pack()
            )
        )
    return row


def navigation_keyboard(back_callback: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row = back_home_row(back_callback)
    if row:
        builder.row(*row)
    return builder.as_markup()


def confirm_keyboard(
    scope: str,
    target_id: int,
    *,
    confirm_text: str = "✅ Confirm",
    cancel_text: str = "❌ Cancel",
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """Two-step confirmation used before destructive or paid actions."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=confirm_text,
            callback_data=ConfirmCB(scope=scope, action="yes", target_id=target_id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=cancel_text,
            callback_data=ConfirmCB(scope=scope, action="no", target_id=target_id).pack(),
        )
    )
    row = back_home_row(back_callback)
    if row:
        builder.row(*row)
    return builder.as_markup()


def single_button_keyboard(text: str, callback_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=callback_data)
    return builder.as_markup()


def rows_keyboard(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        if row:
            builder.row(*row)
    return builder.as_markup()
