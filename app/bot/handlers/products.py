"""Product detail screen: the list of plans for one product."""

from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import ProductCB
from app.bot.handlers.helpers import render
from app.bot.keyboards.store import plans_keyboard
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.registry import Services

router = Router(name="products")


@router.callback_query(ProductCB.filter())
async def open_product(
    callback: CallbackQuery,
    callback_data: ProductCB,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """Show every active plan of a product with price and availability."""
    product = await services.products.get_visible(callback_data.product_id)
    plans = await services.plans.storefront_page(
        product.id, callback_data.page, settings.store.plans_per_page
    )
    # Highlight plans the customer is already waiting for.
    subscribed = {
        plan.id
        for plan in plans.items
        if plan.is_sold_out and await services.notifications.is_subscribed(plan.id, user)
    }
    data = await state.get_data()
    await render(
        callback,
        texts.product_plans(product, plans),
        plans_keyboard(
            product,
            plans,
            store_page=int(data.get("store_page", 1)),
            category_id=int(data.get("store_category", 0)),
            subscribed_plan_ids=subscribed,
        ),
    )
