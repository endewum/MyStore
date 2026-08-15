"""Stock management and the back-in-stock notification system."""

from __future__ import annotations

import pytest

from app.database.models import (
    DeliveryType,
    InventoryStatus,
    NotificationType,
    Plan,
    StockAlertStatus,
    User,
)
from app.services.exceptions import ValidationError
from app.services.registry import Services


async def test_add_stock_increases_availability(
    services: Services, plan: Plan, admin
) -> None:
    change = await services.inventory.add_stock(plan, 10, admin=admin)

    assert change.previous_stock == 5
    assert change.new_stock == 15
    assert change.delta == 10
    assert change.back_in_stock is False
    assert plan.available_quantity == 15


async def test_add_stock_rejects_non_positive(services: Services, plan: Plan) -> None:
    with pytest.raises(ValidationError):
        await services.inventory.add_stock(plan, 0)


async def test_restock_of_sold_out_plan_is_detected(
    services: Services, sold_out_plan: Plan, admin
) -> None:
    change = await services.inventory.add_stock(sold_out_plan, 50, admin=admin)

    assert change.previous_stock == 0
    assert change.new_stock == 50
    assert change.back_in_stock is True
    assert change.became_sold_out is False


async def test_restock_reports_waiting_users(
    services: Services, sold_out_plan: Plan, customer: User, admin
) -> None:
    await services.notifications.subscribe_stock_alert(sold_out_plan, customer)

    change = await services.inventory.add_stock(sold_out_plan, 5, admin=admin)

    assert change.back_in_stock is True
    assert change.waiting_users == 1


async def test_remove_stock_can_make_plan_sold_out(
    services: Services, plan: Plan, admin
) -> None:
    change = await services.inventory.remove_stock(plan, 5, admin=admin)

    assert change.new_stock == 0
    assert change.became_sold_out is True
    assert plan.is_sold_out is True


async def test_remove_stock_never_touches_reserved_units(
    services: Services, customer: User, plan: Plan, admin
) -> None:
    await services.orders.create_order(customer, plan)  # reserves 1 of 5

    change = await services.inventory.remove_stock(plan, 99, admin=admin)

    assert change.new_stock == 1  # the reserved unit survives
    assert plan.reserved_quantity == 1
    assert plan.available_quantity == 0


async def test_remove_stock_requires_unreserved_units(
    services: Services, sold_out_plan: Plan
) -> None:
    with pytest.raises(ValidationError):
        await services.inventory.remove_stock(sold_out_plan, 1)


async def test_set_stock_absolute_value(services: Services, plan: Plan, admin) -> None:
    change = await services.inventory.set_stock(plan, 12, admin=admin)

    assert change.new_stock == 12
    assert plan.stock_quantity == 12


async def test_set_stock_cannot_go_below_reservations(
    services: Services, customer: User, plan: Plan
) -> None:
    await services.orders.create_order(customer, plan)

    with pytest.raises(ValidationError):
        await services.inventory.set_stock(plan, 0)


async def test_import_codes_creates_inventory_and_skips_duplicates(
    services: Services, sold_out_plan: Plan, admin
) -> None:
    change = await services.inventory.import_codes(
        sold_out_plan, ["CODE-1", "CODE-2", "CODE-1"], admin=admin
    )

    assert change.created_items == 2
    assert change.duplicates == 1
    assert change.new_stock == 2
    assert change.back_in_stock is True

    breakdown = await services.inventory.breakdown(sold_out_plan.id)
    assert breakdown[InventoryStatus.AVAILABLE] == 2


async def test_import_rejects_empty_input(services: Services, plan: Plan) -> None:
    with pytest.raises(ValidationError):
        await services.inventory.import_codes(plan, [])


async def test_disabling_an_item_reduces_stock(
    services: Services, code_plan: Plan, admin
) -> None:
    items = await services.inventory.paginate_items(code_plan.id, 1, 10)
    item = items.items[0]

    change = await services.inventory.toggle_item(item, admin=admin)

    assert item.status is InventoryStatus.DISABLED
    assert change.new_stock == 1
    assert code_plan.available_quantity == 1


async def test_reserved_items_cannot_be_deleted(
    services: Services, customer: User, code_plan: Plan, admin
) -> None:
    order = await services.orders.create_order(customer, code_plan)
    reserved = (await services.inventory.items_for_order(order.id))[0]

    with pytest.raises(ValidationError):
        await services.inventory.delete_item(reserved, admin=admin)


async def test_subscribe_only_allowed_for_sold_out_plans(
    services: Services, plan: Plan, customer: User
) -> None:
    with pytest.raises(ValidationError):
        await services.notifications.subscribe_stock_alert(plan, customer)


async def test_subscribe_is_idempotent(
    services: Services, sold_out_plan: Plan, customer: User
) -> None:
    first = await services.notifications.subscribe_stock_alert(sold_out_plan, customer)
    second = await services.notifications.subscribe_stock_alert(sold_out_plan, customer)

    assert first.id == second.id
    assert await services.notifications.waiting_count(sold_out_plan.id) == 1
    assert await services.notifications.is_subscribed(sold_out_plan.id, customer)


async def test_unsubscribe_removes_user_from_waiting_list(
    services: Services, sold_out_plan: Plan, customer: User
) -> None:
    await services.notifications.subscribe_stock_alert(sold_out_plan, customer)

    removed = await services.notifications.unsubscribe_stock_alert(
        sold_out_plan.id, customer
    )

    assert removed is True
    assert await services.notifications.waiting_count(sold_out_plan.id) == 0
    assert await services.notifications.is_subscribed(sold_out_plan.id, customer) is False


async def test_waiting_users_excludes_unreachable_accounts(
    services: Services, sold_out_plan: Plan, customer: User
) -> None:
    await services.notifications.subscribe_stock_alert(sold_out_plan, customer)
    await services.users.mark_bot_blocked(customer.telegram_id)

    waiting = await services.notifications.waiting_users(sold_out_plan.id)

    assert waiting == []


async def test_targeted_notification_closes_the_waiting_list(
    services: Services, sold_out_plan: Plan, customer: User, admin
) -> None:
    await services.notifications.subscribe_stock_alert(sold_out_plan, customer)
    await services.inventory.add_stock(sold_out_plan, 10, admin=admin)
    recipients = await services.notifications.waiting_users(sold_out_plan.id)

    report = await services.notifications.notify_back_in_stock(
        sold_out_plan,
        title="Back in stock",
        body="GPT PLUS 30D is available again.",
        message_text="🔥 BACK IN STOCK",
        recipients=recipients,
        admin=admin,
        interested_only=True,
    )

    assert report.total == 1
    # No bot is attached in tests, so nothing is pushed but everything is stored.
    assert report.sent == 0
    assert await services.notifications.waiting_count(sold_out_plan.id) == 0

    alert = await services.notifications.alerts.get_for_user(
        sold_out_plan.id, customer.id
    )
    assert alert is not None
    assert alert.status is StockAlertStatus.NOTIFIED
    assert alert.notified_at is not None


async def test_notification_is_persisted_in_user_inbox(
    services: Services, sold_out_plan: Plan, customer: User, admin
) -> None:
    await services.notifications.subscribe_stock_alert(sold_out_plan, customer)
    await services.inventory.add_stock(sold_out_plan, 3, admin=admin)
    recipients = await services.notifications.waiting_users(sold_out_plan.id)

    await services.notifications.notify_back_in_stock(
        sold_out_plan,
        title="GPT PLUS 30D is back",
        body="Now available at $3.08.",
        message_text="🔥 BACK IN STOCK",
        recipients=recipients,
        admin=admin,
        interested_only=True,
    )

    inbox = await services.notifications.inbox(customer, 1, 10)
    assert inbox.total == 1
    recipient = inbox.items[0]
    assert recipient.notification.type is NotificationType.STOCK_AVAILABLE
    assert recipient.notification.title == "GPT PLUS 30D is back"
    assert recipient.is_read is False
    assert await services.notifications.unread_count(customer) == 1

    await services.notifications.mark_all_read(customer)
    assert await services.notifications.unread_count(customer) == 0


async def test_broadcast_audience_skips_users_with_alerts_disabled(
    services: Services, customer: User
) -> None:
    await services.users.toggle_notifications(customer)

    notifiable = await services.notifications.notifiable_users()

    assert customer.notifications_enabled is False
    assert notifiable == []


async def test_admin_actions_are_audited(
    services: Services, plan: Plan, admin
) -> None:
    await services.inventory.add_stock(plan, 5, admin=admin)
    await services.inventory.remove_stock(plan, 2, admin=admin)

    logs = await services.store_settings.paginate_logs(1, 10)
    actions = [entry.action.value for entry in logs.items]  # type: ignore[attr-defined]

    assert "ADMIN_ADDED_STOCK" in actions
    assert "ADMIN_REMOVED_STOCK" in actions


async def test_manual_plan_stock_does_not_need_inventory_rows(
    services: Services, plan: Plan, admin
) -> None:
    assert plan.delivery_type is DeliveryType.MANUAL

    await services.inventory.add_stock(plan, 3, admin=admin)
    breakdown = await services.inventory.breakdown(plan.id)

    assert plan.available_quantity == 8
    assert sum(breakdown.values()) == 0
