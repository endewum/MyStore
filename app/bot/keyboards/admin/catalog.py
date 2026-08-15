"""Admin keyboards for products, plans, stock and inventory."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    AdminCB,
    AdminPlanCB,
    AdminProductCB,
    AdminStockCB,
    AdminStockNotifyCB,
)
from app.bot.keyboards.common import back_home_row, pagination_row
from app.database.models import Category, DeliveryType, InventoryItem, Plan, Product
from app.utils.pagination import Page
from app.utils.text import truncate


def products_keyboard(page: Page[Product]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in page.items:
        state = "🟢" if product.is_active else "⚫"
        featured = "🔥" if product.is_featured else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{state}{featured} {truncate(product.name, 26)}",
                callback_data=AdminProductCB(
                    action="view", product_id=product.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminProductCB(action="list", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="➕ Add product", callback_data=AdminProductCB(action="new").pack()
        )
    )
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def product_detail_keyboard(product: Product, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📋 Plans",
            callback_data=AdminPlanCB(
                action="list", product_id=product.id, page=1
            ).pack(),
        ),
        InlineKeyboardButton(
            text="➕ Add plan",
            callback_data=AdminPlanCB(action="new", product_id=product.id).pack(),
        ),
    )
    edit_buttons = [
        InlineKeyboardButton(
            text=label,
            callback_data=AdminProductCB(
                action="field", product_id=product.id, page=page, value=field
            ).pack(),
        )
        for field, label in (
            ("name", "✏️ Name"),
            ("description", "📝 Description"),
            ("emoji", "😀 Emoji"),
            ("category", "🗂 Category"),
        )
    ]
    builder.row(*edit_buttons[:2])
    builder.row(*edit_buttons[2:])
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if product.is_active else "🟢 Enable",
            callback_data=AdminProductCB(
                action="toggle", product_id=product.id, page=page
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🔥 Unfeature" if product.is_featured else "🔥 Feature",
            callback_data=AdminProductCB(
                action="feature", product_id=product.id, page=page
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬆️ Move up",
            callback_data=AdminProductCB(
                action="move", product_id=product.id, page=page, value="up"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="⬇️ Move down",
            callback_data=AdminProductCB(
                action="move", product_id=product.id, page=page, value="down"
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete product",
            callback_data=AdminProductCB(
                action="delete", product_id=product.id, page=page
            ).pack(),
        )
    )
    builder.row(*back_home_row(AdminProductCB(action="list", page=page).pack()))
    return builder.as_markup()


def category_picker_keyboard(
    categories: Sequence[Category], *, callback: str, allow_none: bool = True
) -> InlineKeyboardMarkup:
    """Category chooser reused by the product wizard and edit screens.

    ``callback`` is a template containing ``{id}``.
    """
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(
            text=truncate(category.title, 22),
            callback_data=callback.format(id=category.id),
        )
    if categories:
        builder.adjust(2)
    if allow_none:
        builder.row(
            InlineKeyboardButton(
                text="➖ No category", callback_data=callback.format(id=0)
            )
        )
    return builder.as_markup()


def plans_keyboard(product: Product, page: Page[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in page.items:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{plan.status_icon} {truncate(plan.name, 22)} · "
                    f"{plan.price_display} · {plan.available_quantity}"
                ),
                callback_data=AdminPlanCB(
                    action="view",
                    plan_id=plan.id,
                    product_id=product.id,
                    page=page.page,
                ).pack(),
            )
        )
    nav = pagination_row(
        page,
        lambda target: AdminPlanCB(
            action="list", product_id=product.id, page=target
        ).pack(),
    )
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text="➕ Add plan",
            callback_data=AdminPlanCB(action="new", product_id=product.id).pack(),
        )
    )
    builder.row(
        *back_home_row(
            AdminProductCB(action="view", product_id=product.id, page=1).pack()
        )
    )
    return builder.as_markup()


def plan_detail_keyboard(plan: Plan, *, page: int = 1) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📦 Stock & inventory",
            callback_data=AdminStockCB(action="view", plan_id=plan.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💰 Change price",
            callback_data=AdminPlanCB(
                action="field", plan_id=plan.id, product_id=plan.product_id, value="price"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="⏳ Duration",
            callback_data=AdminPlanCB(
                action="field",
                plan_id=plan.id,
                product_id=plan.product_id,
                value="duration",
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="✏️ Name",
            callback_data=AdminPlanCB(
                action="field", plan_id=plan.id, product_id=plan.product_id, value="name"
            ).pack(),
        ),
        InlineKeyboardButton(
            text="📝 Description",
            callback_data=AdminPlanCB(
                action="field",
                plan_id=plan.id,
                product_id=plan.product_id,
                value="description",
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🚚 Delivery type",
            callback_data=AdminPlanCB(
                action="delivery", plan_id=plan.id, product_id=plan.product_id
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if plan.is_active else "🟢 Enable",
            callback_data=AdminPlanCB(
                action="toggle", plan_id=plan.id, product_id=plan.product_id, page=page
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🔥 Unfeature" if plan.is_featured else "🔥 Feature",
            callback_data=AdminPlanCB(
                action="feature", plan_id=plan.id, product_id=plan.product_id, page=page
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬆️ Move up",
            callback_data=AdminPlanCB(
                action="move",
                plan_id=plan.id,
                product_id=plan.product_id,
                page=page,
                value="up",
            ).pack(),
        ),
        InlineKeyboardButton(
            text="⬇️ Move down",
            callback_data=AdminPlanCB(
                action="move",
                plan_id=plan.id,
                product_id=plan.product_id,
                page=page,
                value="down",
            ).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete plan",
            callback_data=AdminPlanCB(
                action="delete", plan_id=plan.id, product_id=plan.product_id, page=page
            ).pack(),
        )
    )
    builder.row(
        *back_home_row(
            AdminPlanCB(action="list", product_id=plan.product_id, page=page).pack()
        )
    )
    return builder.as_markup()


def delivery_type_keyboard(plan: Plan) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for delivery in DeliveryType:
        mark = "✅ " if plan.delivery_type is delivery else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{mark}{delivery.label}",
                callback_data=AdminPlanCB(
                    action="set_delivery",
                    plan_id=plan.id,
                    product_id=plan.product_id,
                    value=delivery.value,
                ).pack(),
            )
        )
    builder.row(
        *back_home_row(
            AdminPlanCB(
                action="view", plan_id=plan.id, product_id=plan.product_id
            ).pack()
        )
    )
    return builder.as_markup()


def new_plan_delivery_keyboard() -> InlineKeyboardMarkup:
    """Delivery type chooser used inside the "add plan" wizard."""
    builder = InlineKeyboardBuilder()
    for delivery in DeliveryType:
        builder.row(
            InlineKeyboardButton(
                text=delivery.label,
                callback_data=AdminPlanCB(
                    action="wizard_delivery", value=delivery.value
                ).pack(),
            )
        )
    return builder.as_markup()


def stock_keyboard(plan: Plan) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="➕ Add stock",
            callback_data=AdminStockCB(action="add", plan_id=plan.id).pack(),
        ),
        InlineKeyboardButton(
            text="➖ Remove stock",
            callback_data=AdminStockCB(action="remove", plan_id=plan.id).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔢 Set exact stock",
            callback_data=AdminStockCB(action="set", plan_id=plan.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📥 Import codes",
            callback_data=AdminStockCB(action="import", plan_id=plan.id).pack(),
        ),
        InlineKeyboardButton(
            text="📋 View items",
            callback_data=AdminStockCB(action="items", plan_id=plan.id, page=1).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔔 Notify waiting list",
            callback_data=AdminStockNotifyCB(action="menu", plan_id=plan.id).pack(),
        )
    )
    builder.row(
        *back_home_row(
            AdminPlanCB(
                action="view", plan_id=plan.id, product_id=plan.product_id
            ).pack()
        )
    )
    return builder.as_markup()


def inventory_items_keyboard(
    plan: Plan, page: Page[InventoryItem]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in page.items:
        builder.row(
            InlineKeyboardButton(
                text=f"{item.status.label} · {item.masked_value}",
                callback_data=AdminStockCB(
                    action="item", plan_id=plan.id, item_id=item.id, page=page.page
                ).pack(),
            )
        )
    nav = pagination_row(
        page,
        lambda target: AdminStockCB(
            action="items", plan_id=plan.id, page=target
        ).pack(),
    )
    if nav:
        builder.row(*nav)
    builder.row(
        *back_home_row(AdminStockCB(action="view", plan_id=plan.id).pack())
    )
    return builder.as_markup()


def inventory_item_keyboard(
    plan: Plan, item: InventoryItem, *, page: int = 1
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="⚫ Disable" if item.status.value == "AVAILABLE" else "🟢 Enable",
            callback_data=AdminStockCB(
                action="item_toggle", plan_id=plan.id, item_id=item.id, page=page
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🗑 Delete",
            callback_data=AdminStockCB(
                action="item_delete", plan_id=plan.id, item_id=item.id, page=page
            ).pack(),
        ),
    )
    builder.row(
        *back_home_row(
            AdminStockCB(action="items", plan_id=plan.id, page=page).pack()
        )
    )
    return builder.as_markup()


def low_stock_keyboard(page: Page[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in page.items:
        product_name = plan.product.name if plan.product else "—"
        builder.row(
            InlineKeyboardButton(
                text=f"🔴 {truncate(f'{product_name} · {plan.name}', 32)}",
                callback_data=AdminStockCB(action="view", plan_id=plan.id).pack(),
            )
        )
    nav = pagination_row(
        page, lambda target: AdminStockCB(action="low", page=target).pack()
    )
    if nav:
        builder.row(*nav)
    builder.row(*back_home_row(AdminCB(section="home").pack()))
    return builder.as_markup()


def restock_notify_keyboard(plan: Plan, *, waiting: int, all_users: int) -> InlineKeyboardMarkup:
    """Admin decision screen after a plan comes back in stock."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="👁 Preview notification",
            callback_data=AdminStockNotifyCB(action="preview", plan_id=plan.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🔔 Send to waiting list ({waiting})",
            callback_data=AdminStockNotifyCB(
                action="interested", plan_id=plan.id
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"📢 Send to all users ({all_users})",
            callback_data=AdminStockNotifyCB(action="all", plan_id=plan.id).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Don't notify",
            callback_data=AdminStockNotifyCB(action="skip", plan_id=plan.id).pack(),
        )
    )
    return builder.as_markup()
