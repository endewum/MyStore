"""Manual payment submission, approval and rejection."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.database.models import OrderStatus, PaymentMethod, PaymentStatus, Plan, User
from app.services.exceptions import (
    PaymentMethodUnavailable,
    PermissionDeniedError,
    ValidationError,
)
from app.services.registry import Services


async def _pending_order(services: Services, customer: User, plan: Plan):
    return await services.orders.create_order(customer, plan)


async def test_only_configured_methods_are_offered(
    services: Services, session, payment_method: PaymentMethod
) -> None:
    session.add_all(
        [
            PaymentMethod(code="bybit", name="Bybit", is_enabled=True),  # no credentials
            PaymentMethod(
                code="usdt",
                name="USDT",
                account_identifier="TX-wallet",
                is_enabled=False,
            ),
        ]
    )
    await session.flush()

    methods = await services.payments.enabled_methods()

    assert [method.code for method in methods] == ["binance"]


async def test_disabled_method_cannot_be_used(
    services: Services, payment_method: PaymentMethod
) -> None:
    payment_method.is_enabled = False
    await services.session.flush()

    with pytest.raises(PaymentMethodUnavailable):
        await services.payments.get_usable_method(payment_method.id)


async def test_select_method_creates_pending_payment(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    order = await _pending_order(services, customer, plan)

    payment = await services.payments.select_method(order, customer, payment_method)

    assert payment.status is PaymentStatus.PENDING
    assert payment.method_code == "binance"
    assert payment.amount == order.total
    assert order.status is OrderStatus.PENDING_PAYMENT


async def test_select_method_enforces_ownership(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    from aiogram.types import User as TelegramUser

    order = await _pending_order(services, customer, plan)
    other = await services.users.register(
        TelegramUser(id=5555, is_bot=False, first_name="Other")
    )

    with pytest.raises(PermissionDeniedError):
        await services.payments.select_method(order, other, payment_method)


async def test_minimum_amount_is_respected(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    payment_method.min_amount = Decimal("100.00")
    await services.session.flush()
    order = await _pending_order(services, customer, plan)

    with pytest.raises(ValidationError):
        await services.payments.select_method(order, customer, payment_method)


async def test_submit_text_evidence_moves_order_to_review(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)

    payment = await services.payments.submit_evidence(
        order, customer, reference="TX-123456"
    )

    assert payment.status is PaymentStatus.SUBMITTED
    assert payment.reference == "TX-123456"
    assert payment.submitted_at is not None
    assert payment.has_evidence is True
    assert order.status is OrderStatus.PAYMENT_SUBMITTED


async def test_submit_photo_evidence_is_accepted(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)

    payment = await services.payments.submit_evidence(
        order, customer, proof_file_id="file-123", proof_file_unique_id="uniq-123"
    )

    assert payment.proof_file_id == "file-123"
    assert order.status is OrderStatus.PAYMENT_SUBMITTED


async def test_submit_requires_some_evidence(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)

    with pytest.raises(ValidationError):
        await services.payments.submit_evidence(order, customer)


async def test_screenshot_can_be_mandatory(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod
) -> None:
    payment_method.requires_screenshot = True
    await services.session.flush()
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)

    with pytest.raises(ValidationError):
        await services.payments.submit_evidence(order, customer, reference="TX")

    payment = await services.payments.submit_evidence(
        order, customer, reference="TX", proof_file_id="file-1"
    )
    assert payment.status is PaymentStatus.SUBMITTED


async def test_submit_requires_a_selected_method(
    services: Services, customer: User, plan: Plan
) -> None:
    order = await _pending_order(services, customer, plan)

    with pytest.raises(ValidationError):
        await services.payments.submit_evidence(order, customer, reference="TX")


async def test_confirm_payment_marks_order_paid(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod, admin
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX")

    order = await services.payments.confirm(payment, admin)

    assert payment.status is PaymentStatus.CONFIRMED
    assert payment.reviewed_by_telegram_id == admin.telegram_id
    assert payment.reviewed_at is not None
    assert order.status is OrderStatus.PAID
    assert order.paid_at is not None


async def test_confirm_is_not_repeatable(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod, admin
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX")
    await services.payments.confirm(payment, admin)

    with pytest.raises(ValidationError):
        await services.payments.confirm(payment, admin)


async def test_cannot_confirm_a_payment_that_was_never_submitted(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod, admin
) -> None:
    order = await _pending_order(services, customer, plan)
    payment = await services.payments.select_method(order, customer, payment_method)

    with pytest.raises(ValidationError):
        await services.payments.confirm(payment, admin)


async def test_reject_payment_lets_customer_retry(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod, admin
) -> None:
    order = await _pending_order(services, customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX-1")

    order = await services.payments.reject(payment, admin, "Amount did not match")

    assert payment.status is PaymentStatus.REJECTED
    assert payment.rejection_reason == "Amount did not match"
    assert order.status is OrderStatus.PAYMENT_REJECTED
    # Stock stays reserved so the customer can submit again.
    assert plan.reserved_quantity == 1

    retry = await services.payments.select_method(order, customer, payment_method)
    resubmitted = await services.payments.submit_evidence(
        order, customer, reference="TX-2"
    )
    assert retry.id != payment.id
    assert resubmitted.status is PaymentStatus.SUBMITTED
    assert order.status is OrderStatus.PAYMENT_SUBMITTED


async def test_review_queue_lists_submitted_payments_only(
    services: Services, customer: User, plan: Plan, payment_method: PaymentMethod, admin
) -> None:
    plan.stock_quantity = 5
    first = await _pending_order(services, customer, plan)
    await services.payments.select_method(first, customer, payment_method)
    await services.payments.submit_evidence(first, customer, reference="TX-A")

    second = await _pending_order(services, customer, plan)
    await services.payments.select_method(second, customer, payment_method)

    queue = await services.payments.paginate_review_queue(1, 10)

    assert queue.total == 1
    assert await services.payments.count_review_queue() == 1
    assert queue.items[0].order_id == first.id


async def test_payment_method_credentials_come_from_database(
    services: Services, payment_method: PaymentMethod, admin
) -> None:
    await services.payments.update_method(
        payment_method,
        admin=admin,
        account_identifier="987654321",
        network="TRC20",
    )

    method = await services.payments.get_usable_method(payment_method.id)

    assert method.account_identifier == "987654321"
    assert method.network == "TRC20"
    assert method.is_configured is True
