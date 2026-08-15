"""Admin payment review and payment method configuration.

Confirming a payment is always a human decision: this module only records that
decision and moves the order forward.
"""

from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import AdminOrderCB, AdminPaymentCB
from app.bot.filters import IsAdmin
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.orders import (
    payment_method_keyboard,
    payment_methods_keyboard,
    payment_queue_keyboard,
    payment_review_keyboard,
)
from app.bot.keyboards.common import back_home_row, navigation_keyboard
from app.bot.states import PaymentMethodStates, PaymentReviewStates
from app.bot.texts import admin as texts
from app.bot.texts import notifications as notify_texts
from app.config import Settings
from app.database.models import Admin, NotificationType, Order, Payment
from app.services.exceptions import ValidationError
from app.services.registry import Services
from app.utils.logging import get_logger
from app.utils.text import clean_emoji, clean_multiline, clean_text, parse_money

logger = get_logger(__name__)

router = Router(name="admin-payments")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

METHOD_FIELD_PROMPTS: dict[str, str] = {
    "account_identifier": (
        "🔑 Send the account ID, UID or wallet address customers should pay to."
    ),
    "network": "🌐 Send the network name, for example <code>TRC20</code>.",
    "instructions": "📝 Send the instructions shown to customers.",
    "name": "✏️ Send the display name for this method.",
    "emoji": "😀 Send an emoji for this method.",
    "min_amount": "💵 Send the minimum amount, for example <code>5.00</code>.",
}


async def _show_queue(
    event: Message | CallbackQuery, services: Services, settings: Settings, page: int
) -> None:
    result = await services.payments.paginate_review_queue(
        page, settings.store.admin_list_page_size
    )
    await render(event, texts.payment_queue(result), payment_queue_keyboard(result))


async def _show_payment(
    event: Message | CallbackQuery, services: Services, payment_id: int, page: int = 1
) -> None:
    payment = await services.payments.get(payment_id)
    order = await services.orders.get(payment.order_id)
    user = await services.users.get_by_id(payment.user_id)
    await render(
        event,
        texts.payment_review(payment, order, user),
        payment_review_keyboard(payment, page=page),
    )


async def _show_method(
    event: Message | CallbackQuery, services: Services, method_id: int
) -> None:
    method = await services.payments.get_method(method_id)
    await render(
        event, texts.payment_method_detail(method), payment_method_keyboard(method)
    )


def _fulfilment_keyboard(order: Order) -> InlineKeyboardMarkup:
    """Shown to the admin right after a payment is confirmed."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📦 Fulfill Order",
            callback_data=AdminOrderCB(
                action="fulfill", order_id=order.id, page=1, value="fulfil"
            ).pack(),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Cancel order",
            callback_data=AdminOrderCB(
                action="cancel", order_id=order.id, page=1, value="fulfil"
            ).pack(),
        )
    )
    builder.row(*back_home_row(AdminPaymentCB(action="queue", page=1).pack()))
    return builder.as_markup()


# ---------------------------------------------------------------- review queue
@router.callback_query(AdminPaymentCB.filter(F.action == "queue"))
async def open_queue(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    state: FSMContext,
    services: Services,
    settings: Settings,
) -> None:
    await state.clear()
    await _show_queue(callback, services, settings, callback_data.page)


@router.callback_query(AdminPaymentCB.filter(F.action == "view"))
async def view_payment(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_payment(callback, services, callback_data.payment_id, callback_data.page)


@router.callback_query(AdminPaymentCB.filter(F.action == "proof"))
async def view_proof(
    callback: CallbackQuery, callback_data: AdminPaymentCB, services: Services
) -> None:
    payment = await services.payments.get(callback_data.payment_id)
    if not payment.proof_file_id or callback.message is None:
        await answer_callback(callback, "No screenshot was attached.", alert=True)
        return
    await answer_callback(callback)
    await callback.message.answer_photo(
        payment.proof_file_id, caption=f"📸 Proof for payment #{payment.id}"
    )


@router.callback_query(AdminPaymentCB.filter(F.action == "confirm"))
async def confirm_payment(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    admin: Admin,
    services: Services,
) -> None:
    """Approve a payment: the order becomes PAID and moves to fulfilment."""
    payment = await services.payments.get(callback_data.payment_id)
    try:
        order = await services.payments.confirm(payment, admin)
    except ValidationError as error:
        await answer_callback(callback, error.message, alert=True)
        return

    await _notify_customer(services, order, payment, confirmed=True)
    user = await services.users.get_by_id(order.user_id)
    await render(
        callback,
        notify_texts.fulfillment_required(
            order, user.display_name if user else str(order.telegram_id)
        ),
        _fulfilment_keyboard(order),
        answer_text="✅ Payment confirmed.",
    )


@router.callback_query(AdminPaymentCB.filter(F.action == "reject"))
async def ask_rejection_reason(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    state: FSMContext,
    services: Services,
) -> None:
    payment = await services.payments.get(callback_data.payment_id)
    await state.set_state(PaymentReviewStates.waiting_rejection_reason)
    await state.update_data(payment_id=payment.id, page=callback_data.page)
    await render(
        callback,
        "✍️ Send a short rejection reason for the customer.\n\n"
        "Send <code>-</code> to reject without a reason.",
        navigation_keyboard(
            AdminPaymentCB(
                action="view", payment_id=payment.id, page=callback_data.page
            ).pack()
        ),
    )


@router.message(PaymentReviewStates.waiting_rejection_reason, F.text)
async def reject_payment(
    message: Message,
    state: FSMContext,
    admin: Admin,
    services: Services,
    settings: Settings,
) -> None:
    data = await state.get_data()
    payment = await services.payments.get(int(data["payment_id"]))
    raw = (message.text or "").strip()
    reason = None if raw == "-" else raw[:255]
    try:
        order = await services.payments.reject(payment, admin, reason)
    except ValidationError as error:
        await state.clear()
        await message.answer(f"⚠️ {error.message}")
        return

    await state.clear()
    await _notify_customer(services, order, payment, confirmed=False)
    await message.answer(
        f"🚫 Payment for order #{order.order_number} rejected. "
        "The customer has been notified and can submit again."
    )
    await _show_queue(message, services, settings, int(data.get("page", 1)))


async def _notify_customer(
    services: Services, order: Order, payment: Payment, *, confirmed: bool
) -> None:
    user = await services.users.get_by_id(order.user_id)
    if user is None:
        return
    if confirmed:
        text = notify_texts.payment_confirmed(order)
        title = f"Payment confirmed for order #{order.order_number}"
        body = "Your payment was verified. Your order is being prepared."
    else:
        text = notify_texts.payment_rejected(order, payment)
        title = f"Payment rejected for order #{order.order_number}"
        body = payment.rejection_reason or "Please submit your payment again."
    await services.notifications.notify_user(
        user,
        type=NotificationType.PAYMENT_UPDATE,
        title=title,
        body=body,
        message_text=text,
        order_id=order.id,
    )


# --------------------------------------------------------------- payment methods
@router.callback_query(AdminPaymentCB.filter(F.action == "methods"))
async def list_methods(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await state.clear()
    methods = await services.payments.all_methods()
    await render(
        callback, texts.payment_methods(methods), payment_methods_keyboard(methods)
    )


@router.callback_query(AdminPaymentCB.filter(F.action == "method"))
async def view_method(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    state: FSMContext,
    services: Services,
) -> None:
    await state.clear()
    await _show_method(callback, services, callback_data.method_id)


@router.callback_query(AdminPaymentCB.filter(F.action == "toggle"))
async def toggle_method(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    admin: Admin,
    services: Services,
) -> None:
    method = await services.payments.get_method(callback_data.method_id)
    if not method.is_enabled and not method.is_configured:
        await answer_callback(
            callback,
            "Set the account or wallet address before enabling this method.",
            alert=True,
        )
        return
    method = await services.payments.toggle_method(method, admin)
    await render(
        callback,
        texts.payment_method_detail(method),
        payment_method_keyboard(method),
        answer_text="🟢 Enabled" if method.is_enabled else "⚫ Disabled",
    )


@router.callback_query(AdminPaymentCB.filter(F.action == "toggle_proof"))
async def toggle_proof(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    admin: Admin,
    services: Services,
) -> None:
    method = await services.payments.get_method(callback_data.method_id)
    await services.payments.update_method(
        method, admin=admin, requires_screenshot=not method.requires_screenshot
    )
    await _show_method(callback, services, method.id)


@router.callback_query(AdminPaymentCB.filter(F.action == "field"))
async def edit_method_field(
    callback: CallbackQuery,
    callback_data: AdminPaymentCB,
    state: FSMContext,
    services: Services,
) -> None:
    method = await services.payments.get_method(callback_data.method_id)
    prompt = METHOD_FIELD_PROMPTS.get(callback_data.value)
    if prompt is None:
        await answer_callback(callback, "Unsupported field.", alert=True)
        return
    await state.set_state(PaymentMethodStates.waiting_field_value)
    await state.update_data(method_id=method.id, field=callback_data.value)
    await render(
        callback,
        f"{prompt}\n\n⚠️ These details are shown to customers — double-check them "
        "before saving.",
        navigation_keyboard(AdminPaymentCB(action="method", method_id=method.id).pack()),
    )


@router.message(PaymentMethodStates.waiting_field_value, F.text)
async def save_method_field(
    message: Message, state: FSMContext, admin: Admin, services: Services
) -> None:
    data = await state.get_data()
    method = await services.payments.get_method(int(data["method_id"]))
    field = str(data["field"])
    raw = message.text or ""
    try:
        value: str | Decimal
        if field == "min_amount":
            value = parse_money(raw)
        elif field == "instructions":
            value = clean_multiline(raw, max_length=1000, field="instructions")
        elif field == "emoji":
            value = clean_emoji(raw)
        else:
            value = clean_text(raw, max_length=255, field=field.replace("_", " "))
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return

    await services.payments.update_method(method, admin=admin, **{field: value})
    await state.clear()
    await message.answer("✅ Payment method updated.")
    await _show_method(message, services, method.id)
