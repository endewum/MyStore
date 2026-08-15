"""Admin keyboards for user and administrator management."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB, AdminOrderCB, AdminUserCB
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Admin, AdminRole, User
from app.utils.pagination import Page
from app.utils.text import truncate


def users_keyboard(page: Page[User], *, query: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in page.items:
        state = "🚫" if user.is_blocked else ("🟢" if user.is_active else "⚫")
        builder.row(
            InlineKeyboardButton(
                text=truncate(f"{state} {user.display_name}", 32),
                callback_data=AdminUserCB(
                    action="view", user_id=user.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminUserCB(action="list", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="🔎 Find user", callback_data=AdminUserCB(action="search").pack()
        ),
        InlineKeyboardButton(
            text="🛡 Admins", callback_data=AdminUserCB(action="admins").pack()
        ),
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def user_detail_keyboard(user: User, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🧾 Their orders",
            callback_data=AdminOrderCB(
                action="user", order_id=user.id, page=1, value="user"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="✅ Unblock" if user.is_blocked else "🚫 Block",
            callback_data=AdminUserCB(
                action="unblock" if user.is_blocked else "block",
                user_id=user.id,
                page=page,
            ).pack(),
        )
    )
    builder.row(*back_home_row(AdminUserCB(action="list", page=page).pack()))
    return builder.as_markup()


def admins_keyboard(admins: Sequence[Admin]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for admin in admins:
        name = admin.display_name
        builder.row(
            InlineKeyboardButton(
                text=truncate(f"🛡 {name} · {admin.role.value}", 34),
                callback_data=AdminUserCB(
                    action="admin_view", user_id=admin.id
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add admin", callback_data=AdminUserCB(action="grant").pack()
        )
    )
    builder.row(*back_home_row(AdminUserCB(action="list", page=1).pack()))
    return builder.as_markup()


def admin_detail_keyboard(admin: Admin) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    roles = [role for role in AdminRole if role is not admin.role]
    builder.row(
        *[
            InlineKeyboardButton(
                text=f"🔁 {role.value}",
                callback_data=AdminUserCB(
                    action="set_role", user_id=admin.id, value=role.value
                ).pack(),
            )
            for role in roles
        ]
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Revoke access",
            callback_data=AdminUserCB(action="revoke", user_id=admin.id).pack(),
        )
    )
    builder.row(*back_home_row(AdminUserCB(action="admins").pack()))
    return builder.as_markup()


def role_picker_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    """Role chooser shown after an admin enters a new administrator's ID."""
    builder = InlineKeyboardBuilder()
    for role in AdminRole:
        builder.row(
            InlineKeyboardButton(
                text=f"🛡 {role.value}",
                callback_data=AdminUserCB(
                    action="grant_role", user_id=telegram_id, value=role.value
                ).pack(),
            )
        )
    builder.row(*back_home_row(AdminUserCB(action="admins").pack()))
    return builder.as_markup()
