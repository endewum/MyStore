"""Product detail screen: the list of plans for one product."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import ProductCB
from app.bot.handlers.helpers import render
from app.bot.keyboards.store import plans_keyboard, product_sold_out_keyboard
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.registry import Services

router = Router(name="products")


@router.callback_query(ProductCB.filter(F.action == "view"))
async def open_product(
    callback: CallbackQuery,
    callback_data: ProductCB,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """Show every active plan of a product with price and availability."""
    product = await services.products.get_with_plans(callback_data.product_id)
    if not product.is_active:
        from app.services.exceptions import NotFoundError

        raise NotFoundError("This product is no longer available.")
    data = await state.get_data()
    if not product.is_available:
        subscribed = await services.notifications.is_product_subscribed(product.id, user)
        await render(
            callback,
            texts.product_sold_out(product, subscribed=subscribed),
            product_sold_out_keyboard(
                product,
                subscribed=subscribed,
                store_page=int(data.get("store_page", callback_data.page)),
            ),
        )
        return

    plans = await services.plans.storefront_page(
        product.id, callback_data.page, settings.store.plans_per_page
    )
    # Highlight plans the customer is already waiting for.
    subscribed = {
        plan.id
        for plan in plans.items
        if plan.is_sold_out and await services.notifications.is_subscribed(plan.id, user)
    }
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


@router.callback_query(ProductCB.filter(F.action == "notify"))
async def subscribe_product_alert(
    callback: CallbackQuery,
    callback_data: ProductCB,
    state: FSMContext,
    user: User,
    services: Services,
) -> None:
    product = await services.products.get_with_plans(callback_data.product_id)
    await services.notifications.subscribe_product_alert(product, user)
    data = await state.get_data()
    await render(
        callback,
        texts.product_sold_out(product, subscribed=True),
        product_sold_out_keyboard(
            product,
            subscribed=True,
            store_page=int(data.get("store_page", callback_data.page)),
        ),
        answer_text="🔔 You are on the waiting list.",
    )


@router.callback_query(ProductCB.filter(F.action == "unnotify"))
async def unsubscribe_product_alert(
    callback: CallbackQuery,
    callback_data: ProductCB,
    state: FSMContext,
    user: User,
    services: Services,
) -> None:
    await services.notifications.unsubscribe_product_alert(callback_data.product_id, user)
    product = await services.products.get_with_plans(callback_data.product_id)
    data = await state.get_data()
    await render(
        callback,
        texts.product_sold_out(product, subscribed=False),
        product_sold_out_keyboard(
            product,
            subscribed=False,
            store_page=int(data.get("store_page", callback_data.page)),
        ),
        answer_text="🔕 Removed from the waiting list.",
    )
