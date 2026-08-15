"""Plan screens: confirmation, purchase start and stock alerts."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.callbacks import PlanCB
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.orders import payment_methods_keyboard
from app.bot.keyboards.store import (
    plan_detail_keyboard,
    plans_keyboard,
    sold_out_keyboard,
)
from app.bot.texts import customer as texts
from app.config import Settings
from app.database.models import User
from app.services.exceptions import OutOfStockError, ValidationError
from app.services.registry import Services

router = Router(name="plans")


@router.callback_query(PlanCB.filter(F.action == "view"))
async def view_plan(
    callback: CallbackQuery,
    callback_data: PlanCB,
    user: User,
    services: Services,
) -> None:
    """Order confirmation screen, or the sold-out screen with 🔔 Notify Me."""
    plan = await services.plans.get_purchasable(callback_data.plan_id)
    if plan.is_sold_out:
        subscribed = await services.notifications.is_subscribed(plan.id, user)
        await render(
            callback,
            texts.plan_sold_out(plan, subscribed=subscribed),
            sold_out_keyboard(plan, subscribed=subscribed, plans_page=callback_data.page),
        )
        return
    await render(
        callback,
        texts.plan_confirmation(plan),
        plan_detail_keyboard(plan, plans_page=callback_data.page),
    )


@router.callback_query(PlanCB.filter(F.action == "buy"))
async def start_purchase(
    callback: CallbackQuery,
    callback_data: PlanCB,
    state: FSMContext,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """Create the order (PENDING_PAYMENT) and show the payment methods."""
    if not await services.store_settings.get_bool("store_open"):
        await answer_callback(
            callback,
            "🛠 The store is temporarily closed for new orders.",
            alert=True,
        )
        return

    plan = await services.plans.get_purchasable(callback_data.plan_id)
    timeout = await services.store_settings.get_int(
        "payment_timeout_minutes", settings.store.payment_timeout_minutes
    )
    try:
        order = await services.orders.create_order(
            user, plan, expires_in_minutes=timeout
        )
    except OutOfStockError:
        # Someone else took the last unit while this screen was open.
        subscribed = await services.notifications.is_subscribed(plan.id, user)
        await render(
            callback,
            texts.plan_sold_out(plan, subscribed=subscribed),
            sold_out_keyboard(plan, subscribed=subscribed, plans_page=callback_data.page),
            answer_text="This plan just sold out.",
            alert=True,
        )
        return

    await state.clear()
    methods = await services.payments.enabled_methods()
    await render(
        callback,
        texts.payment_methods(order, has_methods=bool(methods)),
        payment_methods_keyboard(order, methods),
        answer_text=f"Order #{order.order_number} created",
    )


@router.callback_query(PlanCB.filter(F.action == "notify"))
async def subscribe_alert(
    callback: CallbackQuery,
    callback_data: PlanCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """Join the waiting list for a sold-out plan."""
    plan = await services.plans.get(callback_data.plan_id)
    try:
        await services.notifications.subscribe_stock_alert(plan, user)
    except ValidationError as error:
        await answer_callback(callback, error.message, alert=True)
        return
    await render(
        callback,
        texts.plan_sold_out(plan, subscribed=True),
        sold_out_keyboard(plan, subscribed=True, plans_page=callback_data.page),
        answer_text="🔔 You are on the waiting list.",
    )


@router.callback_query(PlanCB.filter(F.action == "unnotify"))
async def unsubscribe_alert(
    callback: CallbackQuery,
    callback_data: PlanCB,
    user: User,
    services: Services,
    settings: Settings,
) -> None:
    """Leave the waiting list and return to the plan list."""
    await services.notifications.unsubscribe_stock_alert(callback_data.plan_id, user)
    plan = await services.plans.get(callback_data.plan_id)
    product = plan.product
    plans = await services.plans.storefront_page(
        product.id, callback_data.page, settings.store.plans_per_page
    )
    await render(
        callback,
        texts.product_plans(product, plans),
        plans_keyboard(product, plans, subscribed_plan_ids=set()),
        answer_text="🔕 Removed from the waiting list.",
    )
