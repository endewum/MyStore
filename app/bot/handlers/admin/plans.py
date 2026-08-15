"""Admin plan management."""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import AdminPlanCB, ConfirmCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.catalog import (
    delivery_type_keyboard,
    new_plan_delivery_keyboard,
    plan_detail_keyboard,
    plans_keyboard,
)
from app.bot.keyboards.common import confirm_keyboard, navigation_keyboard
from app.bot.states import PlanStates
from app.bot.texts import admin as texts
from app.config import Settings
from app.database.models import Admin, AdminRole, DeliveryType
from app.services.registry import Services
from app.utils.text import clean_multiline, clean_text, parse_money, parse_positive_int

router = Router(name="admin-plans")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

DELETE_SCOPE = "admin_plan_delete"

FIELD_PROMPTS: dict[str, str] = {
    "name": "✏️ Send the new plan name.",
    "price": "💰 Send the new price, for example <code>15.00</code>.",
    "duration": "⏳ Send the duration, for example <code>6 Months</code>.",
    "description": "📝 Send the new description.",
}


async def _show_plans(
    event: Message | CallbackQuery,
    services: Services,
    settings: Settings,
    product_id: int,
    page: int,
) -> None:
    product = await services.products.get(product_id)
    result = await services.plans.admin_page(
        product_id, page, settings.store.admin_list_page_size
    )
    await render(event, texts.plans_list(product, result), plans_keyboard(product, result))


async def _show_plan(
    event: Message | CallbackQuery, services: Services, plan_id: int, page: int = 1
) -> None:
    plan = await services.plans.get(plan_id)
    waiting = await services.plans.waiting_count(plan.id)
    breakdown = await services.inventory.breakdown(plan.id)
    await render(
        event,
        texts.plan_detail(plan, waiting=waiting, breakdown=breakdown),
        plan_detail_keyboard(plan, page=page),
    )


@router.callback_query(AdminPlanCB.filter(F.action == "list"))
async def list_plans(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_plans(
        callback, services, settings, callback_data.product_id, callback_data.page
    )


@router.callback_query(AdminPlanCB.filter(F.action == "view"))
async def view_plan(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_plan(callback, services, callback_data.plan_id, callback_data.page)


@router.callback_query(AdminPlanCB.filter(F.action == "toggle"))
async def toggle_plan(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    admin: Admin,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await services.plans.toggle_active(plan, admin=admin)
    await _show_plan(callback, services, plan.id, callback_data.page)


@router.callback_query(AdminPlanCB.filter(F.action == "feature"))
async def feature_plan(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    admin: Admin,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await services.plans.toggle_featured(plan, admin=admin)
    await _show_plan(callback, services, plan.id, callback_data.page)


@router.callback_query(AdminPlanCB.filter(F.action == "move"))
async def move_plan(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    admin: Admin,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await services.plans.move(plan, -1 if callback_data.value == "up" else 1, admin=admin)
    await _show_plan(callback, services, plan.id, callback_data.page)


# ------------------------------------------------------------------- delivery type
@router.callback_query(AdminPlanCB.filter(F.action == "delivery"))
async def choose_delivery(
    callback: CallbackQuery, callback_data: AdminPlanCB, services: Services
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await render(
        callback,
        "🚚 <b>Delivery type</b>\n\n"
        "MANUAL — you send the details by hand for each order.\n"
        "CODE / ACCOUNT / INFORMATION — the plan is backed by stored inventory "
        "items that are reserved automatically at checkout.",
        delivery_type_keyboard(plan),
    )


@router.callback_query(AdminPlanCB.filter(F.action == "set_delivery"))
async def set_delivery(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    admin: Admin,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await services.plans.update_plan(
        plan, admin=admin, delivery_type=DeliveryType(callback_data.value)
    )
    await _show_plan(callback, services, plan.id)


# -------------------------------------------------------------------- edit field
@router.callback_query(AdminPlanCB.filter(F.action == "field"))
async def edit_field(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    state: FSMContext,
    services: Services,
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    prompt = FIELD_PROMPTS.get(callback_data.value)
    if prompt is None:
        await answer_callback(callback, "Unsupported field.", alert=True)
        return
    await state.set_state(PlanStates.waiting_field_value)
    await state.update_data(
        plan_id=plan.id, field=callback_data.value, page=callback_data.page
    )
    await render(
        callback,
        prompt,
        navigation_keyboard(
            AdminPlanCB(
                action="view", plan_id=plan.id, product_id=plan.product_id
            ).pack()
        ),
    )


@router.message(PlanStates.waiting_field_value, F.text)
async def save_field(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    plan = await services.plans.get(int(data["plan_id"]))
    field = str(data["field"])
    raw = message.text or ""
    try:
        if field == "price":
            price = parse_money(raw)
            _, previous = await services.plans.change_price(plan, price, admin=admin)
            await state.clear()
            await message.answer(
                f"✅ Price updated: {previous} → {price} {plan.currency}"
            )
            await _show_plan(message, services, plan.id, int(data.get("page", 1)))
            return
        if field == "name":
            value = clean_text(raw, max_length=160, field="name")
        elif field == "duration":
            value = clean_text(raw, max_length=80, field="duration")
        else:
            value = clean_multiline(raw, max_length=1000, field="description")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await services.plans.update_plan(plan, admin=admin, **{field: value})
    await state.clear()
    await message.answer("✅ Plan updated.")
    await _show_plan(message, services, plan.id, int(data.get("page", 1)))


# ----------------------------------------------------------------------- new plan
@router.callback_query(AdminPlanCB.filter(F.action == "new"))
async def new_plan(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    state: FSMContext,
    services: Services,
) -> None:
    product = await services.products.get(callback_data.product_id)
    await state.set_state(PlanStates.waiting_name)
    await state.update_data(product_id=product.id)
    await render(
        callback,
        f"➕ <b>New plan for {product.name}</b>\n\nSend the plan name.\n\n"
        "Send /cancel at any time to stop.",
        navigation_keyboard(
            AdminPlanCB(action="list", product_id=product.id, page=1).pack()
        ),
    )


@router.message(PlanStates.waiting_name, F.text)
async def wizard_name(message: Message, state: FSMContext) -> None:
    try:
        name = clean_text(message.text or "", max_length=160, field="name")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(name=name)
    await state.set_state(PlanStates.waiting_price)
    await message.answer("💰 Send the price, for example <code>15.00</code>.")


@router.message(PlanStates.waiting_price, F.text)
async def wizard_price(message: Message, state: FSMContext) -> None:
    try:
        price = parse_money(message.text or "")
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await state.update_data(price=str(price))
    await state.set_state(PlanStates.waiting_duration)
    await message.answer(
        "⏳ Send the duration, for example <code>1 Month</code> "
        "(or <code>-</code> to skip)."
    )


@router.message(PlanStates.waiting_duration, F.text)
async def wizard_duration(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    duration = None
    if raw != "-":
        try:
            duration = clean_text(raw, max_length=80, field="duration")
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return
    await state.update_data(duration=duration)
    await state.set_state(PlanStates.waiting_stock)
    await message.answer(
        "📦 Send the starting stock quantity (or <code>0</code> to start sold out)."
    )


@router.message(PlanStates.waiting_stock, F.text)
async def wizard_stock(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "0":
        stock = 0
    else:
        try:
            stock = parse_positive_int(raw)
        except ValueError as error:
            await message.answer(f"⚠️ {error}")
            return
    await state.update_data(stock=stock)
    await state.set_state(PlanStates.waiting_delivery_type)
    await message.answer(
        "🚚 Choose how this plan is delivered.",
        reply_markup=new_plan_delivery_keyboard(),
    )


@router.callback_query(
    PlanStates.waiting_delivery_type, AdminPlanCB.filter(F.action == "wizard_delivery")
)
async def wizard_delivery(
    callback: CallbackQuery,
    callback_data: AdminPlanCB,
    state: FSMContext,
    admin: Admin,
    services: Services,
) -> None:
    data = await state.get_data()
    plan = await services.plans.create_plan(
        product_id=int(data["product_id"]),
        name=str(data["name"]),
        price=Decimal(str(data["price"])),
        duration=data.get("duration"),
        delivery_type=DeliveryType(callback_data.value),
        stock_quantity=int(data.get("stock", 0)),
        admin=admin,
    )
    await state.clear()
    await answer_callback(callback, "✅ Plan created.")
    await _show_plan(callback, services, plan.id)


# ------------------------------------------------------------------------- delete
@router.callback_query(AdminPlanCB.filter(F.action == "delete"), IsAdmin(AdminRole.ADMIN))
async def ask_delete(
    callback: CallbackQuery, callback_data: AdminPlanCB, services: Services
) -> None:
    plan = await services.plans.get(callback_data.plan_id)
    await render(
        callback,
        f"🗑 Delete plan <b>{plan.name}</b>?\n\n"
        "Its inventory items will be deleted too. This cannot be undone.",
        confirm_keyboard(
            DELETE_SCOPE,
            plan.id,
            confirm_text="🗑 Yes, delete it",
            back_callback=AdminPlanCB(
                action="view", plan_id=plan.id, product_id=plan.product_id
            ).pack(),
        ),
    )


@router.callback_query(
    ConfirmCB.filter(F.scope == DELETE_SCOPE), IsAdmin(AdminRole.ADMIN)
)
async def confirm_delete(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    admin: Admin,
    services: Services,
    settings: Settings,
) -> None:
    plan = await services.plans.get(callback_data.target_id)
    product_id = plan.product_id
    if callback_data.action == "yes":
        await services.plans.delete_plan(plan, admin=admin)
        await answer_callback(callback, "🗑 Plan deleted.")
        await _show_plans(callback, services, settings, product_id, 1)
        return
    await _show_plan(callback, services, plan.id)
