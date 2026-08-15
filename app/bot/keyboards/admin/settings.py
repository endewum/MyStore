"""Admin keyboards for settings, categories, coupons and the audit log."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminCB, AdminSettingCB
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Category, Coupon, CouponType
from app.services.settings_service import SETTING_KEYS
from app.utils.pagination import Page
from app.utils.text import truncate


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in SETTING_KEYS:
        builder.row(
            InlineKeyboardButton(
                text=f"⚙️ {item.label}",
                callback_data=AdminSettingCB(action="edit", value=item.key).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🗂 Categories",
            callback_data=AdminSettingCB(action="categories", page=1).pack(),
        ),
        InlineKeyboardButton(
            text="🎟 Coupons",
            callback_data=AdminSettingCB(action="coupons", page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📜 Audit log",
            callback_data=AdminSettingCB(action="logs", page=1).pack(),
        )
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def toggle_setting_keyboard(key: str) -> InlineKeyboardMarkup:
    """On/off shortcut for boolean settings."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🟢 ON",
            callback_data=AdminSettingCB(
                action="set_bool", value=f"{key}:on"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="⚫ OFF",
            callback_data=AdminSettingCB(
                action="set_bool", value=f"{key}:off"
            ).pack(),
        ),
    )
    builder.row(*back_home_row(AdminSettingCB(action="menu").pack()))
    return builder.as_markup()


def categories_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        state = "🟢" if category.is_active else "⚫"
        builder.row(
            InlineKeyboardButton(
                text=truncate(f"{state} {category.title}", 30),
                callback_data=AdminSettingCB(
                    action="category", target_id=category.id
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add category",
            callback_data=AdminSettingCB(action="category_new").pack(),
        )
    )
    builder.row(*back_home_row(AdminSettingCB(action="menu").pack()))
    return builder.as_markup()


def category_detail_keyboard(category: Category) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Rename",
            callback_data=AdminSettingCB(
                action="category_field", target_id=category.id, value="name"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="😀 Emoji",
            callback_data=AdminSettingCB(
                action="category_field", target_id=category.id, value="emoji"
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if category.is_active else "🟢 Enable",
            callback_data=AdminSettingCB(
                action="category_toggle", target_id=category.id
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Delete",
            callback_data=AdminSettingCB(
                action="category_delete", target_id=category.id
            ).pack(),
        ),
    )
    builder.row(*back_home_row(AdminSettingCB(action="categories", page=1).pack()))
    return builder.as_markup()


def coupons_keyboard(page: Page[Coupon]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for coupon in page.items:
        state = "🟢" if coupon.is_usable else "⚫"
        value = (
            f"{coupon.value:g}%"
            if coupon.type is CouponType.PERCENT
            else f"${coupon.value:,.2f}"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"{state} {truncate(coupon.code, 18)} · {value}",
                callback_data=AdminSettingCB(
                    action="coupon", target_id=coupon.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminSettingCB(action="coupons", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="➕ Add coupon",
            callback_data=AdminSettingCB(action="coupon_new").pack(),
        )
    )
    builder.row(*back_home_row(AdminSettingCB(action="menu").pack()))
    return builder.as_markup()


def coupon_detail_keyboard(coupon: Coupon, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if coupon.is_active else "🟢 Enable",
            callback_data=AdminSettingCB(
                action="coupon_toggle", target_id=coupon.id, page=page
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Delete",
            callback_data=AdminSettingCB(
                action="coupon_delete", target_id=coupon.id, page=page
            ).pack(),
        ),
    )
    builder.row(*back_home_row(AdminSettingCB(action="coupons", page=page).pack()))
    return builder.as_markup()


def coupon_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="％ Percentage",
            callback_data=AdminSettingCB(
                action="coupon_type", value=CouponType.PERCENT.value
            ).pack(),
        ),
        InlineKeyboardButton(
            text="💵 Fixed amount",
            callback_data=AdminSettingCB(
                action="coupon_type", value=CouponType.FIXED.value
            ).pack(),
        ),
    )
    builder.row(*back_home_row(AdminSettingCB(action="coupons", page=1).pack()))
    return builder.as_markup()


def logs_keyboard(page: Page[object]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = pagination_row(
        page, lambda target: AdminSettingCB(action="logs", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(*back_home_row(AdminSettingCB(action="menu").pack()))
    return builder.as_markup()
