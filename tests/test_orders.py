"""Order creation, state machine, stock reservation and ownership."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.database.models import (
    ORDER_NUMBER_OFFSET,
    InventoryStatus,
    OrderStatus,
    Plan,
    User,
)
from app.services.exceptions import (
    InvalidStateTransition,
    OutOfStockError,
    PermissionDeniedError,
    ValidationError,
)
from app.services.order_service import ALLOWED_TRANSITIONS, can_transition
from app.services.registry import Services


async def test_create_order_reserves_stock(
    services: Services, customer: User, plan: Plan
) -> None:
    order = await services.orders.create_order(customer, plan)

    assert order.status is OrderStatus.PENDING_PAYMENT
    assert order.total == Decimal("15.00")
    assert order.order_number.isdigit()
    assert int(order.order_number) > 10_000
    assert order.expires_at is not None

    assert plan.stock_quantity == 5
    assert plan.reserved_quantity == 1
    assert plan.available_quantity == 4


async def test_order_snapshots_plan_details(
    services: Services, customer: User, plan: Plan
) -> None:
    order = await services.orders.create_order(customer, plan)
    item = order.item

    assert item is not None
    assert item.product_name == "ChatGPT"
    assert item.plan_name == "GPT TEAM"
    assert item.duration == "6 Months"
    assert item.unit_price == Decimal("15.00")

    # Renaming the plan later must not rewrite order history.
    await services.plans.update_plan(plan, name="GPT TEAM v2")
    assert item.plan_name == "GPT TEAM"


async def test_cannot_order_sold_out_plan(
    services: Services, customer: User, sold_out_plan: Plan
) -> None:
    with pytest.raises(OutOfStockError):
        await services.orders.create_order(customer, sold_out_plan)


async def test_failed_checkout_leaves_no_order_row(
    services: Services, customer: User, sold_out_plan: Plan
) -> None:
    """Stock is taken before the order is inserted, so a rejected checkout
    cannot leave an orphan order behind."""
    with pytest.raises(OutOfStockError):
        await services.orders.create_order(customer, sold_out_plan)

    assert (await services.orders.paginate_admin(None, 1, 10)).total == 0


async def test_order_numbers_are_unique_and_derived_from_the_id(
    services: Services, customer: User, plan: Plan
) -> None:
    """Numbers come from the primary key, so concurrent checkouts cannot collide."""
    orders = [await services.orders.create_order(customer, plan) for _ in range(3)]

    numbers = [order.order_number for order in orders]
    assert len(set(numbers)) == 3
    assert all(not number.startswith("tmp-") for number in numbers)
    assert numbers == [
        str(order.id + ORDER_NUMBER_OFFSET) for order in orders
    ]


async def test_last_unit_race_is_rejected(
    services: Services, customer: User, plan: Plan
) -> None:
    plan.stock_quantity = 1
    await services.session.flush()

    await services.orders.create_order(customer, plan)

    with pytest.raises(OutOfStockError):
        await services.orders.create_order(customer, plan)


async def test_code_plan_reserves_inventory_items(
    services: Services, customer: User, code_plan: Plan
) -> None:
    order = await services.orders.create_order(customer, code_plan)

    items = await services.inventory.items_for_order(order.id)
    assert len(items) == 1
    assert items[0].status is InventoryStatus.RESERVED
    assert items[0].order_id == order.id

    breakdown = await services.inventory.breakdown(code_plan.id)
    assert breakdown[InventoryStatus.AVAILABLE] == 1
    assert breakdown[InventoryStatus.RESERVED] == 1


async def test_blocked_user_cannot_order(
    services: Services, customer: User, plan: Plan, admin
) -> None:
    await services.users.set_blocked(customer, True, admin=admin, reason="fraud")

    with pytest.raises(PermissionDeniedError):
        await services.orders.create_order(customer, plan)


async def test_order_ownership_is_enforced(
    services: Services, customer: User, plan: Plan
) -> None:
    from aiogram.types import User as TelegramUser

    order = await services.orders.create_order(customer, plan)
    intruder = await services.users.register(
        TelegramUser(id=7777, is_bot=False, first_name="Nosy")
    )

    with pytest.raises(PermissionDeniedError):
        await services.orders.get_for_user(order.id, intruder)

    owned = await services.orders.get_for_user(order.id, customer)
    assert owned.id == order.id


async def test_state_machine_rejects_invalid_transitions(
    services: Services, customer: User, plan: Plan
) -> None:
    order = await services.orders.create_order(customer, plan)

    # A pending order cannot jump straight to PAID or DELIVERED.
    with pytest.raises(InvalidStateTransition):
        await services.orders.transition(order, OrderStatus.PAID)
    with pytest.raises(InvalidStateTransition):
        await services.orders.transition(order, OrderStatus.DELIVERED)

    assert order.status is OrderStatus.PENDING_PAYMENT


async def test_terminal_states_are_closed() -> None:
    assert ALLOWED_TRANSITIONS[OrderStatus.CANCELLED] == frozenset()
    assert ALLOWED_TRANSITIONS[OrderStatus.REFUNDED] == frozenset()
    assert can_transition(OrderStatus.DELIVERED, OrderStatus.REFUNDED)
    assert not can_transition(OrderStatus.DELIVERED, OrderStatus.PAID)
    assert not can_transition(OrderStatus.CANCELLED, OrderStatus.PENDING_PAYMENT)


async def test_transition_writes_history(
    services: Services, customer: User, plan: Plan
) -> None:
    order = await services.orders.create_order(customer, plan)
    await services.orders.cancel_by_customer(order, customer)

    history = await services.orders.history_for_order(order.id)
    transitions = [(entry.from_status, entry.to_status) for entry in history]  # type: ignore[attr-defined]

    assert (None, OrderStatus.PENDING_PAYMENT) in transitions
    assert (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED) in transitions


async def test_cancel_releases_reserved_stock(
    services: Services, customer: User, code_plan: Plan
) -> None:
    order = await services.orders.create_order(customer, code_plan)
    assert code_plan.reserved_quantity == 1

    await services.orders.cancel_by_customer(order, customer)

    assert code_plan.reserved_quantity == 0
    assert code_plan.available_quantity == 2
    breakdown = await services.inventory.breakdown(code_plan.id)
    assert breakdown[InventoryStatus.AVAILABLE] == 2
    assert breakdown[InventoryStatus.RESERVED] == 0


async def test_customer_cannot_cancel_after_payment_submitted(
    services: Services, customer: User, plan: Plan, payment_method
) -> None:
    order = await services.orders.create_order(customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    await services.payments.submit_evidence(order, customer, reference="TX1")

    with pytest.raises(ValidationError):
        await services.orders.cancel_by_customer(order, customer)


async def test_cancel_is_idempotent_for_stock(
    services: Services, customer: User, plan: Plan, admin
) -> None:
    order = await services.orders.create_order(customer, plan)
    await services.orders.cancel_by_customer(order, customer)

    # A second release must not push reserved_quantity negative.
    await services.orders.inventory.release_for_order(order)

    assert plan.reserved_quantity == 0


async def test_fulfillment_consumes_stock_and_delivers(
    services: Services, customer: User, code_plan: Plan, admin, payment_method
) -> None:
    order = await services.orders.create_order(customer, code_plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(
        order, customer, reference="TX-OK"
    )
    await services.payments.confirm(payment, admin)

    order = await services.orders.fulfill(order, admin, "CODE-001")

    assert order.status is OrderStatus.DELIVERED
    assert order.delivery_content == "CODE-001"
    assert order.delivered_at is not None
    assert code_plan.sold_quantity == 1
    assert code_plan.stock_quantity == 1
    assert code_plan.reserved_quantity == 0

    items = await services.inventory.items_for_order(order.id)
    assert items[0].status is InventoryStatus.SOLD
    assert items[0].sold_at is not None


async def test_fulfillment_requires_paid_order(
    services: Services, customer: User, plan: Plan, admin
) -> None:
    order = await services.orders.create_order(customer, plan)

    with pytest.raises(InvalidStateTransition):
        await services.orders.fulfill(order, admin, "details")


async def test_fulfillment_rejects_empty_delivery(
    services: Services, customer: User, plan: Plan, admin, payment_method
) -> None:
    order = await services.orders.create_order(customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX")
    await services.payments.confirm(payment, admin)

    with pytest.raises(ValidationError):
        await services.orders.fulfill(order, admin, "   ")


async def test_auto_delivery_preview_lists_reserved_codes(
    services: Services, customer: User, code_plan: Plan
) -> None:
    order = await services.orders.create_order(customer, code_plan)

    preview = await services.orders.auto_delivery_preview(order)

    assert preview == "CODE-001"


async def test_refund_releases_stock_after_delivery(
    services: Services, customer: User, plan: Plan, admin, payment_method
) -> None:
    order = await services.orders.create_order(customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX")
    await services.payments.confirm(payment, admin)
    await services.orders.fulfill(order, admin, "account:secret")

    order = await services.orders.refund(order, admin, "Customer request")

    assert order.status is OrderStatus.REFUNDED
    assert plan.sold_quantity == 1


async def test_expired_pending_orders_are_cancelled(
    services: Services, customer: User, plan: Plan
) -> None:
    from datetime import timedelta

    from app.utils.time import utcnow

    order = await services.orders.create_order(customer, plan)
    order.expires_at = utcnow() - timedelta(minutes=5)
    await services.session.flush()

    expired = await services.orders.expire_stale_orders()

    assert [item.id for item in expired] == [order.id]
    assert order.status is OrderStatus.CANCELLED
    assert plan.reserved_quantity == 0


async def test_order_pagination_for_user(
    services: Services, customer: User, plan: Plan
) -> None:
    plan.stock_quantity = 10
    await services.session.flush()
    for _ in range(7):
        await services.orders.create_order(customer, plan)

    first = await services.orders.paginate_for_user(customer, 1, 5)
    second = await services.orders.paginate_for_user(customer, 2, 5)

    assert first.total == 7
    assert len(first.items) == 5
    assert len(second.items) == 2
    assert first.items[0].id > first.items[-1].id  # newest first


async def test_coupon_applies_discount(
    services: Services, customer: User, plan: Plan, admin
) -> None:
    from app.database.models import CouponType

    await services.store_settings.create_coupon(
        code="SAVE10", type=CouponType.PERCENT, value=Decimal("10"), admin=admin
    )

    order = await services.orders.create_order(customer, plan, coupon_code="save10")

    assert order.subtotal == Decimal("15.00")
    assert order.discount == Decimal("1.50")
    assert order.total == Decimal("13.50")
    assert order.coupon_code == "SAVE10"


async def test_unknown_coupon_is_rejected(
    services: Services, customer: User, plan: Plan
) -> None:
    with pytest.raises(ValidationError):
        await services.orders.create_order(customer, plan, coupon_code="NOPE")
