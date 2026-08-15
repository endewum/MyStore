"""Storefront keyboards: the product grid, categories and plan lists."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    CategoryCB,
    MenuCB,
    PlanCB,
    ProductCB,
    SearchCB,
    StoreCB,
)
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Category, Plan, Product
from app.utils.pagination import Page
from app.utils.text import truncate


def storefront_keyboard(
    page: Page[Product],
    *,
    columns: int = 3,
    category_id: int = 0,
    show_categories: bool = True,
) -> InlineKeyboardMarkup:
    """Products laid out in a compact grid (3 columns by default)."""
    builder = InlineKeyboardBuilder()
    for product in page.items:
        builder.button(
            text=truncate(product.button_title, 18),
            callback_data=ProductCB(product_id=product.id, page=page.page).pack(),
        )
    if page.items:
        builder.adjust(columns)

    nav = pagination_row(
        page,
        lambda target: StoreCB(page=target, category=category_id).pack(),
    )
    if nav:
        builder.row(*nav)

    extras: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text="🔎 Search", callback_data=SearchCB(action="start").pack()
        )
    ]
    if show_categories:
        extras.append(
            InlineKeyboardButton(
                text="🗂 Categories", callback_data=CategoryCB(page=1).pack()
            )
        )
    if category_id:
        extras.append(
            InlineKeyboardButton(
                text="🧹 Clear filter", callback_data=StoreCB(page=1, category=0).pack()
            )
        )
    builder.row(*extras)
    builder.row(*back_home_row(MenuCB(action="home").pack(), back_text="◀️ Back"))
    return builder.as_markup()


def categories_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    """One category per row, plus an "all products" shortcut."""
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(
            InlineKeyboardButton(
                text=truncate(category.title, 28),
                callback_data=StoreCB(page=1, category=category.id).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🏪 All products", callback_data=StoreCB(page=1, category=0).pack()
        )
    )
    builder.row(*back_home_row(StoreCB(page=1, category=0).pack()))
    return builder.as_markup()


def plans_keyboard(
    product: Product,
    page: Page[Plan],
    *,
    store_page: int = 1,
    category_id: int = 0,
    subscribed_plan_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    """One button per plan: buy when in stock, otherwise "Notify Me"."""
    subscribed = subscribed_plan_ids or set()
    builder = InlineKeyboardBuilder()
    for plan in page.items:
        if plan.is_purchasable:
            label = f"🟢 {truncate(plan.name, 26)} — {plan.price_display}"
            callback = PlanCB(action="view", plan_id=plan.id, page=page.page).pack()
        elif plan.id in subscribed:
            label = f"🔔 Waiting — {truncate(plan.name, 22)}"
            callback = PlanCB(action="unnotify", plan_id=plan.id, page=page.page).pack()
        else:
            label = f"🔔 Notify me — {truncate(plan.name, 22)}"
            callback = PlanCB(action="notify", plan_id=plan.id, page=page.page).pack()
        builder.row(InlineKeyboardButton(text=label, callback_data=callback))

    nav = pagination_row(
        page, lambda target: ProductCB(product_id=product.id, page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(
        *back_home_row(StoreCB(page=store_page, category=category_id).pack())
    )
    return builder.as_markup()


def plan_detail_keyboard(plan: Plan, *, plans_page: int = 1) -> InlineKeyboardMarkup:
    """Confirmation screen for a purchasable plan."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Continue",
            callback_data=PlanCB(action="buy", plan_id=plan.id, page=plans_page).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=ProductCB(product_id=plan.product_id, page=plans_page).pack(),
        )
    )
    return builder.as_markup()


def sold_out_keyboard(plan: Plan, *, subscribed: bool, plans_page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if subscribed:
        builder.row(
            InlineKeyboardButton(
                text="🔕 Stop waiting",
                callback_data=PlanCB(
                    action="unnotify", plan_id=plan.id, page=plans_page
                ).pack(),
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔔 Notify Me",
                callback_data=PlanCB(
                    action="notify", plan_id=plan.id, page=plans_page
                ).pack(),
            )
        )
    builder.row(
        *back_home_row(ProductCB(product_id=plan.product_id, page=plans_page).pack())
    )
    return builder.as_markup()


def search_results_keyboard(page: Page[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in page.items:
        builder.row(
            InlineKeyboardButton(
                text=truncate(f"{product.emoji} {product.name}", 30),
                callback_data=ProductCB(product_id=product.id, page=1).pack(),
            )
        )
    nav = pagination_row(page, lambda target: SearchCB(action="page", page=target).pack())
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="🔎 New search", callback_data=SearchCB(action="start").pack()
        )
    )
    builder.row(*back_home_row(StoreCB(page=1, category=0).pack()))
    return builder.as_markup()


def buy_now_keyboard(plan: Plan) -> InlineKeyboardMarkup:
    """Attached to restock notifications and promotional broadcasts."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🛒 BUY NOW",
            callback_data=PlanCB(action="view", plan_id=plan.id, page=1).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏪 Store", callback_data=StoreCB(page=1, category=0).pack()
        )
    )
    return builder.as_markup()


def open_store_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🛍 Open Store", callback_data=StoreCB(page=1, category=0).pack()
        )
    )
    return builder.as_markup()
