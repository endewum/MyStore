"""Customer payment flow.

Nothing in this module verifies a payment: the customer receives the admin's
configured transfer details, sends the money outside Telegram, then submits
evidence which an administrator reviews by hand.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import PayCB
from app.bot.handlers.helpers import answer_callback, render
from app.bot.keyboards.admin.orders import payment_review_keyboard
from app.bot.keyboards.orders import (
    order_detail_keyboard,
    order_submitted_keyboard,
    payment_instructions_keyboard,
    payment_methods_keyboard,
    payment_submitting_keyboard,
)
from app.bot.states import PaymentStates
from app.bot.texts import customer as texts
from app.bot.texts import notifications as notify_texts
from app.database.models import Order, User
from app.services.exceptions import ValidationError
from app.services.registry import Services
from app.utils.logging import get_logger
from app.utils.text import clean_multiline

logger = get_logger(__name__)

router = Router(name="payments")

#: Longest transaction reference / note we accept from a customer.
MAX_REFERENCE_LENGTH = 250


@router.callback_query(PayCB.filter(F.action == "choose"))
async def choose_method(
    callback: CallbackQuery,
    callback_data: PayCB,
    state: FSMContext,
    user: User,
    services: Services,
) -> None:
    """List the enabled payment channels for an unpaid order."""
    await state.clear()
    order = await services.orders.get_for_user(callback_data.order_id, user)
    methods = await services.payments.enabled_methods()
    await render(
        callback,
        texts.payment_methods(order, has_methods=bool(methods)),
        payment_methods_keyboard(order, methods),
    )


@router.callback_query(PayCB.filter(F.action == "method"))
async def show_instructions(
    callback: CallbackQuery,
    callback_data: PayCB,
    user: User,
    services: Services,
) -> None:
    """Show the configured account/wallet details for the chosen channel."""
    order = await services.orders.get_for_user(callback_data.order_id, user)
    method = await services.payments.get_usable_method(callback_data.method_id)
    await services.payments.select_method(order, user, method)
    await render(
        callback,
        texts.payment_instructions(order, method),
        payment_instructions_keyboard(order, method),
    )


@router.callback_query(PayCB.filter(F.action == "paid"))
async def request_evidence(
    callback: CallbackQuery,
    callback_data: PayCB,
    state: FSMContext,
    user: User,
    services: Services,
) -> None:
    """Ask the customer for their transaction details."""
    order = await services.orders.get_for_user(callback_data.order_id, user)
    payment = await services.payments.latest_for_order(order.id)
    method = payment.method if payment else None
    await state.set_state(PaymentStates.waiting_evidence)
    await state.update_data(order_id=order.id)
    await render(
        callback,
        texts.payment_evidence_prompt(order, method),
        payment_submitting_keyboard(order),
    )


@router.callback_query(PayCB.filter(F.action == "cancel"))
async def cancel_submission(
    callback: CallbackQuery,
    callback_data: PayCB,
    state: FSMContext,
    user: User,
    services: Services,
) -> None:
    await state.clear()
    order = await services.orders.get_for_user(callback_data.order_id, user)
    payment = await services.payments.latest_for_order(order.id)
    await render(
        callback,
        texts.order_detail(order, payment=payment),
        order_detail_keyboard(order),
        answer_text="Submission cancelled.",
    )


@router.message(PaymentStates.waiting_evidence, F.photo)
async def submit_photo_evidence(
    message: Message, state: FSMContext, user: User, services: Services
) -> None:
    """Accept a screenshot, optionally with a caption as the reference."""
    photo = message.photo[-1] if message.photo else None
    caption = (message.caption or "").strip()
    await _finalize_submission(
        message,
        state,
        user,
        services,
        reference=caption[:MAX_REFERENCE_LENGTH] or None,
        proof_file_id=photo.file_id if photo else None,
        proof_file_unique_id=photo.file_unique_id if photo else None,
    )


@router.message(PaymentStates.waiting_evidence, F.text)
async def submit_text_evidence(
    message: Message, state: FSMContext, user: User, services: Services
) -> None:
    """Accept a transaction ID / reference as text."""
    try:
        reference = clean_multiline(
            message.text or "", max_length=MAX_REFERENCE_LENGTH, field="reference"
        )
    except ValueError as error:
        await message.answer(f"⚠️ {error}")
        return
    await _finalize_submission(
        message, state, user, services, reference=reference, proof_file_id=None
    )


@router.message(PaymentStates.waiting_evidence)
async def reject_other_evidence(message: Message) -> None:
    await message.answer(
        "⚠️ Please send your transaction ID as text, or a screenshot photo."
    )


async def _finalize_submission(
    message: Message,
    state: FSMContext,
    user: User,
    services: Services,
    *,
    reference: str | None,
    proof_file_id: str | None,
    proof_file_unique_id: str | None = None,
) -> None:
    data = await state.get_data()
    order_id = int(data.get("order_id", 0))
    if not order_id:
        await state.clear()
        await message.answer("⚠️ That payment session expired. Please start again.")
        return

    order = await services.orders.get_for_user(order_id, user)
    try:
        payment = await services.payments.submit_evidence(
            order,
            user,
            reference=reference,
            proof_file_id=proof_file_id,
            proof_file_unique_id=proof_file_unique_id,
        )
    except ValidationError as error:
        await message.answer(f"⚠️ {error.message}")
        return

    await state.clear()
    await message.answer(
        texts.payment_submitted(order, payment),
        reply_markup=order_submitted_keyboard(order),
    )
    await _alert_admins(message, order, services, user)


async def _alert_admins(
    message: Message, order: Order, services: Services, user: User
) -> None:
    """Push the review card to every administrator."""
    payment = await services.payments.latest_for_order(order.id)
    if payment is None or services.dispatcher is None:
        return
    text = notify_texts.new_payment_for_review(order, payment, user.display_name)
    keyboard = payment_review_keyboard(payment)
    for telegram_id in await services.users.admin_telegram_ids():
        result = await services.dispatcher.send(
            telegram_id, text, reply_markup=keyboard
        )
        if not result.ok:
            logger.warning(
                "admin_alert.failed", telegram_id=telegram_id, error=result.error
            )
        elif payment.proof_file_id:
            await services.dispatcher.send(
                telegram_id,
                f"📸 Payment proof for order #{order.order_number}",
                photo_file_id=payment.proof_file_id,
            )
