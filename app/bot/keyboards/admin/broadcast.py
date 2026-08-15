"""Admin broadcast keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminBroadcastCB, AdminCB
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Broadcast, BroadcastAudience
from app.utils.pagination import Page
from app.utils.text import truncate


def broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✍️ New broadcast",
            callback_data=AdminBroadcastCB(action="new").pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🕘 History",
            callback_data=AdminBroadcastCB(action="history", page=1).pack(),
        )
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def audience_keyboard() -> InlineKeyboardMarkup:
    """Audience chooser shown after the message content is captured."""
    builder = InlineKeyboardBuilder()
    for audience in (
        BroadcastAudience.ACTIVE_USERS,
        BroadcastAudience.ALL_USERS,
        BroadcastAudience.CUSTOMERS,
    ):
        builder.row(
            InlineKeyboardButton(
                text=audience.label,
                callback_data=AdminBroadcastCB(
                    action="audience", value=audience.value
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel", callback_data=AdminBroadcastCB(action="menu").pack()
        )
    )
    return builder.as_markup()


def preview_keyboard(broadcast: Broadcast) -> InlineKeyboardMarkup:
    """Final confirmation before a campaign goes out."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"📢 SEND to {broadcast.total_recipients} user(s)",
            callback_data=AdminBroadcastCB(
                action="send", broadcast_id=broadcast.id
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=AdminBroadcastCB(
                action="cancel", broadcast_id=broadcast.id
            ).pack(),
        )
    )
    return builder.as_markup()


def history_keyboard(page: Page[Broadcast]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for broadcast in page.items:
        builder.row(
            InlineKeyboardButton(
                text=truncate(
                    f"{broadcast.status.label} · {broadcast.sent_count}/"
                    f"{broadcast.total_recipients} · {broadcast.body}",
                    36,
                ),
                callback_data=AdminBroadcastCB(
                    action="view", broadcast_id=broadcast.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminBroadcastCB(action="history", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(*back_home_row(AdminBroadcastCB(action="menu").pack()))
    return builder.as_markup()


def broadcast_detail_keyboard(broadcast: Broadcast, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data=AdminBroadcastCB(
                action="view", broadcast_id=broadcast.id, page=page
            ).pack(),
        )
    )
    builder.row(
        *back_home_row(AdminBroadcastCB(action="history", page=page).pack())
    )
    return builder.as_markup()
