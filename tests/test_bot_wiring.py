"""Callback data, keyboards, pagination and dispatcher wiring."""

from __future__ import annotations

from datetime import datetime

import pytest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TelegramUser

from app.bot.callbacks import (
    AdminPlanCB,
    AdminStockCB,
    MenuCB,
    OrderCB,
    PayCB,
    PlanCB,
    ProductCB,
    StoreCB,
)
from app.bot.filters import IsAdmin
from app.bot.keyboards.common import home_keyboard, pagination_row
from app.bot.keyboards.store import plans_keyboard, storefront_keyboard
from app.bot.texts import customer as customer_texts
from app.database.models import AdminRole, Plan, Product
from app.services.registry import Services
from app.utils.pagination import Page, normalize_page
from app.utils.text import esc, money, parse_money, parse_positive_int, slugify

#: Telegram rejects callback payloads longer than 64 bytes.
CALLBACK_LIMIT = 64


@pytest.mark.parametrize(
    "callback",
    [
        MenuCB(action="notifications"),
        StoreCB(page=99, category=999999),
        ProductCB(product_id=999999999, page=99),
        PlanCB(action="unnotify", plan_id=999999999, page=99),
        OrderCB(action="cancel", order_id=999999999, page=99),
        PayCB(action="method", order_id=999999999, method_id=99999),
        AdminPlanCB(
            action="set_delivery",
            plan_id=999999999,
            product_id=999999999,
            page=99,
            value="INFORMATION",
        ),
        AdminStockCB(action="item_toggle", plan_id=999999, page=99, item_id=999999999),
    ],
)
def test_callback_payloads_fit_telegram_limit(callback: CallbackData) -> None:
    packed = callback.pack()

    assert len(packed.encode()) <= CALLBACK_LIMIT


def test_callback_roundtrip() -> None:
    packed = PlanCB(action="buy", plan_id=42, page=3).pack()

    restored = PlanCB.unpack(packed)

    assert restored.action == "buy"
    assert restored.plan_id == 42
    assert restored.page == 3


def test_invalid_callback_data_is_rejected() -> None:
    """Malformed payloads must raise, never silently decode into defaults."""
    with pytest.raises((ValueError, TypeError)):
        PlanCB.unpack("pl:buy:not-a-number:1")
    with pytest.raises((ValueError, TypeError)):
        PlanCB.unpack("totally-unrelated")


def test_storefront_uses_three_column_grid(product: Product) -> None:
    page = Page(items=[product] * 7, page=1, per_page=27, total=7)

    markup = storefront_keyboard(page, columns=3)
    widths = [len(row) for row in markup.inline_keyboard]

    assert widths[:3] == [3, 3, 1]
    # Footer rows: search/categories, then back/home.
    assert widths[-1] == 2


def test_storefront_shows_pagination_only_when_needed(product: Product) -> None:
    single = storefront_keyboard(
        Page(items=[product], page=1, per_page=27, total=1), columns=3
    )
    multi = storefront_keyboard(
        Page(items=[product] * 27, page=2, per_page=27, total=60), columns=3
    )

    single_labels = [button.text for row in single.inline_keyboard for button in row]
    multi_labels = [button.text for row in multi.inline_keyboard for button in row]

    assert not any("Page" in label or "Next" in label for label in single_labels)
    assert "◀️ Previous" in multi_labels
    assert "Next ➡️" in multi_labels
    assert "📄 2/3" in multi_labels


def test_pagination_row_is_empty_for_single_page() -> None:
    row = pagination_row(
        Page(items=[], page=1, per_page=10, total=4), lambda page: f"x:{page}"
    )

    assert row == []


def test_sold_out_plan_gets_notify_button(
    product: Product, plan: Plan, sold_out_plan: Plan
) -> None:
    page = Page(items=[plan, sold_out_plan], page=1, per_page=8, total=2)

    markup = plans_keyboard(product, page)
    labels = [button.text for row in markup.inline_keyboard for button in row]
    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]

    assert any(label.startswith("🟢") for label in labels)
    assert any("Notify me" in label for label in labels)
    assert PlanCB(action="view", plan_id=plan.id, page=1).pack() in callbacks
    assert PlanCB(action="notify", plan_id=sold_out_plan.id, page=1).pack() in callbacks


def test_subscribed_plan_offers_to_stop_waiting(
    product: Product, sold_out_plan: Plan
) -> None:
    page = Page(items=[sold_out_plan], page=1, per_page=8, total=1)

    markup = plans_keyboard(product, page, subscribed_plan_ids={sold_out_plan.id})
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert any("Waiting" in label for label in labels)


def test_home_keyboard_hides_admin_button_for_customers() -> None:
    customer_view = home_keyboard(is_admin=False)
    admin_view = home_keyboard(is_admin=True, unread=3, pending_orders=2)

    customer_labels = [b.text for row in customer_view.inline_keyboard for b in row]
    admin_labels = [b.text for row in admin_view.inline_keyboard for b in row]

    assert "⚙️ Admin Panel" not in customer_labels
    assert "⚙️ Admin Panel" in admin_labels
    assert "🔔 Notifications (3)" in admin_labels
    assert "📦 My Orders (2)" in admin_labels


def test_normalize_page_clamps_range() -> None:
    assert normalize_page(0, total=100, per_page=10) == 1
    assert normalize_page(50, total=100, per_page=10) == 10
    assert normalize_page(3, total=100, per_page=10) == 3
    assert normalize_page(3, total=0, per_page=10) == 1


def test_plan_screen_shows_stock_and_price(product: Product, plan: Plan, sold_out_plan: Plan) -> None:
    page = Page(items=[plan, sold_out_plan], page=1, per_page=8, total=2)

    text = customer_texts.product_plans(product, page)

    assert "CHATGPT" in text
    assert "$15.00" in text
    assert "5 available" in text
    assert "❌ Sold Out" in text
    assert "🟢" in text and "🔴" in text


def test_order_confirmation_states_manual_review(plan: Plan) -> None:
    text = customer_texts.plan_confirmation(plan)

    assert "ORDER CONFIRMATION" in text
    assert "$15.00" in text
    assert "reviewed manually" in text


def test_html_is_escaped_in_messages(product: Product, plan: Plan) -> None:
    product.name = "Evil <script>alert(1)</script>"
    page = Page(items=[plan], page=1, per_page=8, total=1)

    text = customer_texts.product_plans(product, page)

    assert "<script>" not in text
    assert "&lt;SCRIPT&gt;" in text


def test_text_helpers() -> None:
    assert slugify("Microsoft 365 Family!") == "microsoft-365-family"
    assert money(3.5) == "$3.50"
    assert money(3.5, "EUR") == "3.50 EUR"
    assert esc("<b>") == "&lt;b&gt;"
    assert parse_money("$1,234.50") == pytest.approx(1234.50)
    assert parse_positive_int("25") == 25

    with pytest.raises(ValueError):
        parse_money("free")
    with pytest.raises(ValueError):
        parse_positive_int("0")
    with pytest.raises(ValueError):
        parse_positive_int("-4")


def _callback(user_id: int) -> CallbackQuery:
    chat = Chat(id=user_id, type="private")
    from_user = TelegramUser(id=user_id, is_bot=False, first_name="Someone")
    message = Message(
        message_id=1, date=datetime(2026, 1, 1), chat=chat, from_user=from_user
    )
    return CallbackQuery(
        id="1", from_user=from_user, chat_instance="1", data="a:home", message=message
    )


async def test_is_admin_filter_requires_role(services: Services, admin) -> None:
    event = _callback(admin.telegram_id)

    assert await IsAdmin()(event, admin=admin) is True
    assert await IsAdmin(AdminRole.SUPER_ADMIN)(event, admin=admin) is True
    assert await IsAdmin()(event, admin=None) is False


async def test_is_admin_filter_honours_role_hierarchy(services: Services) -> None:
    staff = await services.users.grant_admin(8008, AdminRole.STAFF)
    event = _callback(staff.telegram_id)

    assert await IsAdmin()(event, admin=staff) is True
    assert await IsAdmin(AdminRole.ADMIN)(event, admin=staff) is False


async def test_inactive_admin_loses_access(services: Services) -> None:
    admin = await services.users.grant_admin(8009, AdminRole.ADMIN)
    admin.is_active = False

    assert await IsAdmin()(_callback(8009), admin=admin) is False


def test_dispatcher_registers_all_routers(settings) -> None:
    from app.bot.bootstrap import create_dispatcher
    from app.database.session import Database

    settings.db.url = "sqlite+aiosqlite:///:memory:"
    dispatcher = create_dispatcher(settings, Database(settings.db))

    names = {router.name for router in dispatcher.sub_routers[0].sub_routers}
    assert "admin" in names
    assert {"start", "store", "products", "plans", "orders", "payments"} <= names
