"""End-to-end flows through the real dispatcher.

Synthetic Telegram updates are fed to the configured ``Dispatcher`` with a fake
API session, so middlewares, filters, FSM states, keyboards and services all run
exactly as they do in production — only the network is replaced.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio

from app.database.models import (
    AdminRole,
    Category,
    DeliveryType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Plan,
    Product,
)
from app.services.registry import Services
from tests.conftest import BotHarness
from tests.fakes import message_update, photo_update, press_update

#: Routers are process-wide singletons, so the whole module shares one loop.
pytestmark = pytest.mark.asyncio(loop_scope="session")

CUSTOMER_ID = 500_001
ADMIN_ID = 500_002
INTRUDER_ID = 500_099


@pytest_asyncio.fixture(loop_scope="session")
async def store(bot_harness: BotHarness) -> AsyncIterator[BotHarness]:
    """A clean store: one product, one available plan, one sold-out plan."""
    await bot_harness.reset()
    async with bot_harness.database.session() as db_session:
        category = Category(name="AI", slug="ai", emoji="🤖", sort_order=10)
        db_session.add(category)
        await db_session.flush()

        product = Product(
            name="ChatGPT",
            slug="chatgpt",
            emoji="🤖",
            description="AI subscriptions",
            category_id=category.id,
            is_featured=True,
            sort_order=10,
        )
        db_session.add(product)
        await db_session.flush()

        db_session.add_all(
            [
                Plan(
                    product_id=product.id,
                    name="GPT TEAM",
                    duration="6 Months",
                    price=Decimal("15.00"),
                    stock_quantity=24,
                    delivery_type=DeliveryType.MANUAL,
                    sort_order=10,
                ),
                Plan(
                    product_id=product.id,
                    name="GPT PLUS 30D",
                    duration="30 Days",
                    price=Decimal("3.08"),
                    stock_quantity=0,
                    delivery_type=DeliveryType.ACCOUNT,
                    sort_order=20,
                ),
                PaymentMethod(
                    code="binance",
                    name="Binance",
                    emoji="🟡",
                    account_identifier="123456789",
                    instructions="Send USDT to the Binance ID above.",
                    is_enabled=True,
                    sort_order=10,
                ),
            ]
        )
        services = Services(db_session, bot_harness.settings)
        await services.users.grant_admin(
            ADMIN_ID, AdminRole.SUPER_ADMIN, username="boss"
        )
        await services.store_settings.ensure_defaults()

    bot_harness.session.clear()
    yield bot_harness


async def _walk_to_payment_methods(store: BotHarness) -> None:
    """Drive a customer from /start to the payment-method screen."""
    session = store.session
    await store.feed(message_update("/start", CUSTOMER_ID))
    await store.feed(press_update("m:store", CUSTOMER_ID))
    await store.feed(
        press_update(
            session.find_callback(r"^p:\d+:view", CUSTOMER_ID), CUSTOMER_ID
        )
    )
    await store.feed(
        press_update(session.find_callback(r"^pl:view", CUSTOMER_ID), CUSTOMER_ID)
    )
    await store.feed(
        press_update(session.find_callback(r"^pl:buy", CUSTOMER_ID), CUSTOMER_ID)
    )


async def _submit_payment(store: BotHarness, reference: str = "TXID-ABC123") -> None:
    session = store.session
    await store.feed(
        press_update(session.find_callback(r"^pay:method", CUSTOMER_ID), CUSTOMER_ID)
    )
    await store.feed(
        press_update(session.find_callback(r"^pay:paid", CUSTOMER_ID), CUSTOMER_ID)
    )
    await store.feed(message_update(reference, CUSTOMER_ID, update_id=20))


async def test_dispatcher_registers_every_router(store: BotHarness) -> None:
    root = store.dispatcher.sub_routers[0]
    names = {router.name for router in root.sub_routers}

    assert "admin" in names
    assert {
        "start",
        "store",
        "products",
        "plans",
        "orders",
        "payments",
        "account",
        "notifications",
        "fallback",
    } <= names


async def test_configured_admin_lands_in_admin_panel_on_start(store: BotHarness) -> None:
    await store.feed(message_update("/start", ADMIN_ID))

    assert "ADMIN PANEL" in store.session.last_text(ADMIN_ID)
    assert "⚙️ Admin Panel" not in store.session.button_labels(ADMIN_ID)
    assert "🛍 Products" in store.session.button_labels(ADMIN_ID)


async def test_customer_journey_to_manual_payment_review(store: BotHarness) -> None:
    """Home → store → product → plan → order → payment → evidence submitted."""
    session = store.session

    await store.feed(message_update("/start", CUSTOMER_ID))
    assert "Digital Store" in session.last_text(CUSTOMER_ID)

    session.clear()
    await store.feed(press_update("m:store", CUSTOMER_ID))
    assert "STORE" in session.last_text(CUSTOMER_ID)
    store_screen = session.last_text(CUSTOMER_ID)
    assert "Tap a product to see its plans" in store_screen
    labels = session.button_labels(CUSTOMER_ID)
    assert any("ChatGPT" in label and label.startswith("🟢") for label in labels)

    product_cb = session.find_callback(r"^p:\d+:view", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(product_cb, CUSTOMER_ID))
    plans_screen = session.last_text(CUSTOMER_ID)
    assert "CHATGPT" in plans_screen
    assert "24 available" in plans_screen
    assert "Sold Out" in plans_screen

    view_cb = session.find_callback(r"^pl:view", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(view_cb, CUSTOMER_ID))
    assert "ORDER CONFIRMATION" in session.last_text(CUSTOMER_ID)

    buy_cb = session.find_callback(r"^pl:buy", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(buy_cb, CUSTOMER_ID))
    payment_screen = session.last_text(CUSTOMER_ID)
    assert "PAYMENT" in payment_screen
    assert "$15.00" in payment_screen
    assert any("Binance" in label for label in session.button_labels(CUSTOMER_ID))

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = (await services.orders.paginate_admin(None, 1, 10)).items[0]
        assert order.status is OrderStatus.PENDING_PAYMENT
        assert order.item is not None
        assert order.item.plan_name == "GPT TEAM"
        plan = await services.plans.get(order.item.plan_id or 0)
        assert plan.reserved_quantity == 1
        assert plan.available_quantity == 23

    method_cb = session.find_callback(r"^pay:method", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(method_cb, CUSTOMER_ID))
    instructions = session.last_text(CUSTOMER_ID)
    assert "BINANCE PAYMENT" in instructions
    assert "123456789" in instructions
    assert "verified manually" in instructions

    paid_cb = session.find_callback(r"^pay:paid", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(paid_cb, CUSTOMER_ID))
    assert "SUBMIT PAYMENT DETAILS" in session.last_text(CUSTOMER_ID)

    session.clear()
    await store.feed(photo_update(CUSTOMER_ID, caption="TXID-ABC123", update_id=2))
    assert any("PAYMENT SUBMITTED" in text for text in session.texts(CUSTOMER_ID))
    admin_texts = session.texts(ADMIN_ID)
    assert any("PAYMENT REVIEW" in text for text in admin_texts)
    assert any("TXID-ABC123" in text for text in admin_texts)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = (await services.orders.paginate_admin(None, 1, 10)).items[0]
        payment = await services.payments.latest_for_order(order.id)
        assert order.status is OrderStatus.PAYMENT_SUBMITTED
        assert payment is not None
        assert payment.status is PaymentStatus.SUBMITTED
        assert payment.reference == "TXID-ABC123"
        assert payment.proof_file_id == "proof-file-id"


async def test_admin_confirms_payment_and_fulfils_order(store: BotHarness) -> None:
    """Admin review → PAID → manual fulfilment → customer receives delivery."""
    session = store.session
    await _walk_to_payment_methods(store)
    await _submit_payment(store, "TXID-XYZ")

    confirm_cb = session.find_callback(r"^apay:confirm", ADMIN_ID)
    session.clear()
    await store.feed(press_update(confirm_cb, ADMIN_ID))
    assert "FULFILLMENT REQUIRED" in session.last_text(ADMIN_ID)
    assert any("PAYMENT CONFIRMED" in text for text in session.texts(CUSTOMER_ID))

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = (await services.orders.paginate_admin(None, 1, 10)).items[0]
        assert order.status is OrderStatus.PAID
        assert order.paid_at is not None

    fulfill_cb = session.find_callback(r"^ao:fulfill", ADMIN_ID)
    session.clear()
    await store.feed(press_update(fulfill_cb, ADMIN_ID))
    assert "FULFILL ORDER" in session.last_text(ADMIN_ID)

    session.clear()
    await store.feed(
        message_update("login: buyer@example.com\npassword: s3cret", ADMIN_ID, 21)
    )
    customer_messages = session.texts(CUSTOMER_ID)
    assert any("ORDER COMPLETED" in text for text in customer_messages)
    assert any("buyer@example.com" in text for text in customer_messages)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = (await services.orders.paginate_admin(None, 1, 10)).items[0]
        assert order.status is OrderStatus.DELIVERED
        assert order.delivery_content is not None
        plan = await services.plans.get(order.item.plan_id or 0)
        assert plan.sold_quantity == 1
        assert plan.stock_quantity == 23
        assert plan.reserved_quantity == 0


async def test_admin_rejects_payment_and_customer_can_retry(store: BotHarness) -> None:
    session = store.session
    await _walk_to_payment_methods(store)
    await _submit_payment(store, "TXID-BAD")

    reject_cb = session.find_callback(r"^apay:reject", ADMIN_ID)
    session.clear()
    await store.feed(press_update(reject_cb, ADMIN_ID))
    assert "rejection reason" in session.last_text(ADMIN_ID)

    session.clear()
    await store.feed(message_update("Amount did not match", ADMIN_ID, 22))
    assert any("PAYMENT REJECTED" in text for text in session.texts(CUSTOMER_ID))
    assert any(
        "Amount did not match" in text for text in session.texts(CUSTOMER_ID)
    )

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = (await services.orders.paginate_admin(None, 1, 10)).items[0]
        payment = await services.payments.latest_for_order(order.id)
        assert order.status is OrderStatus.PAYMENT_REJECTED
        assert payment is not None
        assert payment.status is PaymentStatus.REJECTED
        # Stock stays reserved so the customer can pay again.
        plan = await services.plans.get(order.item.plan_id or 0)
        assert plan.reserved_quantity == 1


async def test_notify_me_then_restock_notification(store: BotHarness) -> None:
    """Sold-out plan → 🔔 Notify Me → admin restock → waiting list notified."""
    session = store.session

    await store.feed(message_update("/start", CUSTOMER_ID))
    await store.feed(press_update("m:store", CUSTOMER_ID))
    await store.feed(
        press_update(
            session.find_callback(r"^p:\d+:view", CUSTOMER_ID), CUSTOMER_ID
        )
    )
    notify_cb = session.find_callback(r"^pl:notify", CUSTOMER_ID)
    session.clear()
    await store.feed(press_update(notify_cb, CUSTOMER_ID))
    assert "waiting list" in session.last_text(CUSTOMER_ID)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        user = await services.users.get_by_telegram_id(CUSTOMER_ID)
        sold_out = next(
            plan
            for plan in await services.plans.list_for_product(1)
            if plan.name == "GPT PLUS 30D"
        )
        assert await services.notifications.is_subscribed(sold_out.id, user) is True

    # Admin restocks through the panel: sold-out list → stock screen → add.
    session.clear()
    await store.feed(message_update("/admin", ADMIN_ID))
    await store.feed(press_update("ast:low:0:1:0", ADMIN_ID))
    await store.feed(
        press_update(session.find_callback(r"^ast:view", ADMIN_ID), ADMIN_ID)
    )
    add_cb = session.find_callback(r"^ast:add", ADMIN_ID)
    session.clear()
    await store.feed(press_update(add_cb, ADMIN_ID))
    assert "added" in session.last_text(ADMIN_ID)

    session.clear()
    await store.feed(message_update("50", ADMIN_ID, update_id=23))
    report = "\n".join(session.texts(ADMIN_ID))
    assert "STOCK UPDATED" in report
    assert "back in stock" in report
    assert "Nothing has been sent yet" in report
    # Crucially, adding stock alone must not message anyone.
    assert session.texts(CUSTOMER_ID) == []

    preview_cb = session.find_callback(r"^asn:preview", ADMIN_ID)
    session.clear()
    await store.feed(press_update(preview_cb, ADMIN_ID))
    assert "PREVIEW" in session.last_text(ADMIN_ID)
    assert session.texts(CUSTOMER_ID) == []

    send_cb = session.find_callback(r"^asn:interested", ADMIN_ID)
    session.clear()
    await store.feed(press_update(send_cb, ADMIN_ID))
    assert any("back" in text.lower() for text in session.texts(CUSTOMER_ID))
    assert "NOTIFICATION SENT" in session.last_text(ADMIN_ID)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        user = await services.users.get_by_telegram_id(CUSTOMER_ID)
        restocked = next(
            plan
            for plan in await services.plans.list_for_product(1)
            if plan.name == "GPT PLUS 30D"
        )
        assert restocked.stock_quantity == 50
        assert await services.notifications.waiting_count(restocked.id) == 0
        assert (await services.notifications.inbox(user, 1, 10)).total == 1


async def test_admin_broadcast_reaches_users(store: BotHarness) -> None:
    session = store.session
    await store.feed(message_update("/start", CUSTOMER_ID))
    await store.feed(message_update("/admin", ADMIN_ID))

    session.clear()
    await store.feed(press_update("ab:menu:0:1:", ADMIN_ID))
    await store.feed(
        press_update(session.find_callback(r"^ab:new", ADMIN_ID), ADMIN_ID)
    )
    assert "NEW BROADCAST" in session.last_text(ADMIN_ID)

    session.clear()
    await store.feed(message_update("🔥 NEW STOCK AVAILABLE!", ADMIN_ID, 24))
    audience_cb = session.find_callback(r"^ab:audience", ADMIN_ID)

    session.clear()
    await store.feed(press_update(audience_cb, ADMIN_ID))
    preview = session.last_text(ADMIN_ID)
    assert "PREVIEW" in preview
    assert "NEW STOCK AVAILABLE" in preview
    assert "Estimated delivery" in preview
    assert "Nothing has been sent yet" in preview


async def test_non_admin_cannot_open_admin_panel(store: BotHarness) -> None:
    await store.feed(message_update("/admin", CUSTOMER_ID))

    assert "restricted" in store.session.last_text(CUSTOMER_ID)


async def test_non_admin_callback_to_admin_screen_is_denied(store: BotHarness) -> None:
    await store.feed(message_update("/start", CUSTOMER_ID))

    store.session.clear()
    await store.feed(press_update("ap:list:0:1:", CUSTOMER_ID))

    assert store.session.answered_callbacks(), "the tap must be acknowledged"
    assert not any("PRODUCTS" in text for text in store.session.texts(CUSTOMER_ID))


async def test_stale_callback_data_is_handled(store: BotHarness) -> None:
    await store.feed(message_update("/start", CUSTOMER_ID))

    store.session.clear()
    await store.feed(press_update("pl:view:999999:1", CUSTOMER_ID))

    assert any("no longer" in alert for alert in store.session.alerts())


async def test_unknown_callback_prefix_does_not_crash(store: BotHarness) -> None:
    await store.feed(message_update("/start", CUSTOMER_ID))

    store.session.clear()
    await store.feed(press_update("totally:bogus:data", CUSTOMER_ID))

    assert store.session.answered_callbacks()


async def test_order_ownership_is_enforced_through_the_bot(store: BotHarness) -> None:
    await _walk_to_payment_methods(store)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order_id = (await services.orders.paginate_admin(None, 1, 10)).items[0].id

    await store.feed(message_update("/start", INTRUDER_ID))
    store.session.clear()
    await store.feed(press_update(f"o:view:{order_id}:1", INTRUDER_ID))

    assert any(
        "does not belong to you" in alert for alert in store.session.alerts()
    )
    assert not any("ORDER #" in text for text in store.session.texts(INTRUDER_ID))


async def test_search_flow_returns_matching_product(store: BotHarness) -> None:
    session = store.session
    await store.feed(message_update("/start", CUSTOMER_ID))

    session.clear()
    await store.feed(message_update("/search", CUSTOMER_ID, update_id=25))
    assert "SEARCH" in session.last_text(CUSTOMER_ID)

    session.clear()
    await store.feed(message_update("chatgpt", CUSTOMER_ID, update_id=26))
    assert "result(s) for" in session.last_text(CUSTOMER_ID)
    assert session.find_callback(r"^p:\d+", CUSTOMER_ID)


async def test_search_with_no_match_is_friendly(store: BotHarness) -> None:
    session = store.session
    await store.feed(message_update("/start", CUSTOMER_ID))
    await store.feed(message_update("/search", CUSTOMER_ID, update_id=27))

    session.clear()
    await store.feed(message_update("nonexistent thing", CUSTOMER_ID, update_id=28))

    assert "No products matched" in session.last_text(CUSTOMER_ID)


async def test_customer_can_cancel_unpaid_order_and_stock_returns(
    store: BotHarness,
) -> None:
    session = store.session
    await _walk_to_payment_methods(store)

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order_id = (await services.orders.paginate_admin(None, 1, 10)).items[0].id

    session.clear()
    await store.feed(press_update(f"o:cancel:{order_id}:1", CUSTOMER_ID))
    assert "Cancel order" in session.last_text(CUSTOMER_ID)

    await store.feed(press_update(f"cf:order_cancel:yes:{order_id}", CUSTOMER_ID))

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        order = await services.orders.get(order_id)
        plan = await services.plans.get(order.item.plan_id or 0)
        assert order.status is OrderStatus.CANCELLED
        assert plan.reserved_quantity == 0
        assert plan.available_quantity == 24


async def test_my_orders_and_notifications_screens(store: BotHarness) -> None:
    session = store.session
    await _walk_to_payment_methods(store)

    session.clear()
    await store.feed(press_update("o:list:0:1", CUSTOMER_ID))
    orders_screen = session.last_text(CUSTOMER_ID)
    assert "MY ORDERS" in orders_screen
    assert "$15.00" in orders_screen

    session.clear()
    await store.feed(press_update("nt:list:1:0", CUSTOMER_ID))
    assert "NOTIFICATIONS" in session.last_text(CUSTOMER_ID)

    session.clear()
    await store.feed(press_update("acc:home:1", CUSTOMER_ID))
    account_screen = session.last_text(CUSTOMER_ID)
    assert "MY ACCOUNT" in account_screen
    assert str(CUSTOMER_ID) in account_screen


async def test_admin_dashboard_shows_live_counters(store: BotHarness) -> None:
    session = store.session
    await _walk_to_payment_methods(store)
    await store.feed(message_update("/admin", ADMIN_ID))

    session.clear()
    await store.feed(press_update("a:dashboard:1", ADMIN_ID))
    dashboard = session.last_text(ADMIN_ID)

    assert "DASHBOARD" in dashboard
    assert "Users:" in dashboard
    assert "Orders:" in dashboard
    assert "Sold-out plans:" in dashboard


async def test_admin_can_configure_payment_method(store: BotHarness) -> None:
    session = store.session
    await store.feed(message_update("/admin", ADMIN_ID))

    session.clear()
    await store.feed(press_update("apay:methods:0:0:1:", ADMIN_ID))
    assert "PAYMENT METHODS" in session.last_text(ADMIN_ID)

    method_cb = session.find_callback(r"^apay:method:", ADMIN_ID)
    session.clear()
    await store.feed(press_update(method_cb, ADMIN_ID))
    assert "BINANCE" in session.last_text(ADMIN_ID)

    field_cb = session.find_callback(r"^apay:field:.*account_identifier", ADMIN_ID)
    session.clear()
    await store.feed(press_update(field_cb, ADMIN_ID))
    assert "wallet address" in session.last_text(ADMIN_ID)

    session.clear()
    await store.feed(message_update("987654321", ADMIN_ID, update_id=29))
    assert "updated" in session.last_text(ADMIN_ID).lower() or any(
        "987654321" in text for text in session.texts(ADMIN_ID)
    )

    async with store.database.session() as db_session:
        services = Services(db_session, store.settings)
        method = (await services.payments.all_methods())[0]
        assert method.account_identifier == "987654321"
