"""Product listing, pagination, search and plan visibility."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.database.models import Category, Plan, Product
from app.services.exceptions import NotFoundError, ValidationError
from app.services.registry import Services


async def _bulk_products(session, count: int, category_id: int | None = None) -> None:
    session.add_all(
        [
            Product(
                name=f"Product {index:02d}",
                slug=f"product-{index:02d}",
                emoji="🛍",
                category_id=category_id,
                sort_order=100 + index,
            )
            for index in range(count)
        ]
    )
    await session.flush()


async def test_storefront_lists_active_products(
    services: Services, product: Product, session
) -> None:
    session.add(Product(name="Hidden", slug="hidden", is_active=False))
    await session.flush()

    page = await services.products.storefront_page(1, 27)

    names = [item.name for item in page.items]
    assert "ChatGPT" in names
    assert "Hidden" not in names


async def test_featured_products_come_first(services: Services, product: Product, session) -> None:
    session.add(Product(name="Aardvark", slug="aardvark", sort_order=1))
    await session.flush()

    page = await services.products.storefront_page(1, 27)

    # ChatGPT is featured, so it outranks a lower sort_order product.
    assert page.items[0].name == "ChatGPT"


async def test_storefront_pagination(services: Services, session) -> None:
    await _bulk_products(session, 30)

    first = await services.products.storefront_page(1, 27)
    second = await services.products.storefront_page(2, 27)

    assert first.total == 30
    assert len(first.items) == 27
    assert first.total_pages == 2
    assert first.has_next is True
    assert first.has_previous is False
    assert len(second.items) == 3
    assert second.has_next is False
    assert second.label == "2/2"


async def test_pagination_clamps_out_of_range_page(services: Services, session) -> None:
    await _bulk_products(session, 5)

    page = await services.products.storefront_page(99, 27)

    assert page.page == 1
    assert len(page.items) == 5


async def test_storefront_filters_by_category(
    services: Services, product: Product, category: Category, session
) -> None:
    await _bulk_products(session, 3, category_id=None)

    filtered = await services.products.storefront_page(1, 27, category.id)

    assert [item.name for item in filtered.items] == ["ChatGPT"]


async def test_missing_product_raises(services: Services) -> None:
    with pytest.raises(NotFoundError):
        await services.products.get_visible(4242)


async def test_inactive_product_is_not_visible(services: Services, product: Product) -> None:
    await services.products.toggle_product(product)

    with pytest.raises(NotFoundError):
        await services.products.get_visible(product.id)


async def test_search_matches_product_plan_and_category(
    services: Services, product: Product, plan: Plan, category: Category
) -> None:
    by_product = await services.products.search("chatgpt", 1, 10)
    by_plan = await services.products.search("GPT TEAM", 1, 10)
    by_category = await services.products.search("AI", 1, 10)

    assert [item.id for item in by_product.items] == [product.id]
    assert [item.id for item in by_plan.items] == [product.id]
    assert product.id in [item.id for item in by_category.items]


async def test_search_requires_two_characters(services: Services) -> None:
    with pytest.raises(ValidationError):
        await services.products.search("a", 1, 10)


async def test_plan_listing_hides_inactive_plans(
    services: Services, product: Product, plan: Plan, sold_out_plan: Plan
) -> None:
    await services.plans.toggle_active(sold_out_plan)

    page = await services.plans.storefront_page(product.id, 1, 8)

    assert [item.id for item in page.items] == [plan.id]


async def test_sold_out_plan_is_listed_but_not_purchasable(
    services: Services, product: Product, sold_out_plan: Plan
) -> None:
    page = await services.plans.storefront_page(product.id, 1, 8)

    listed = next(item for item in page.items if item.id == sold_out_plan.id)
    assert listed.is_sold_out is True
    assert listed.is_purchasable is False
    assert listed.status_icon == "🔴"
    assert listed.price_display == "$3.08"


async def test_plan_availability_accounts_for_reservations(plan: Plan) -> None:
    plan.reserved_quantity = 2

    assert plan.stock_quantity == 5
    assert plan.available_quantity == 3
    assert plan.is_purchasable is True

    plan.reserved_quantity = 5
    assert plan.available_quantity == 0
    assert plan.is_sold_out is True


async def test_duplicate_plan_name_rejected(
    services: Services, product: Product, plan: Plan, admin
) -> None:
    with pytest.raises(ValidationError):
        await services.plans.create_plan(
            product_id=product.id,
            name=plan.name,
            price=Decimal("1.00"),
            admin=admin,
        )


async def test_create_product_generates_unique_slug(services: Services, admin) -> None:
    first = await services.products.create_product(
        name="Canva Pro", description=None, emoji="🎨", category_id=None, admin=admin
    )
    second = await services.products.create_product(
        name="Canva Pro", description=None, emoji="🎨", category_id=None, admin=admin
    )

    assert first.slug == "canva-pro"
    assert second.slug == "canva-pro-2"


async def test_change_price_returns_previous_value(
    services: Services, plan: Plan, admin
) -> None:
    _, previous = await services.plans.change_price(plan, Decimal("19.99"), admin=admin)

    assert previous == Decimal("15.00")
    assert plan.price == Decimal("19.99")


async def test_product_button_title_marks_availability_and_featured(
    services: Services, product: Product, plan: Plan
) -> None:
    loaded = await services.products.get_with_plans(product.id)
    assert loaded.button_title == "🟢 🔥 ChatGPT"
    loaded.is_featured = False
    assert loaded.button_title == "🟢 ChatGPT"


async def test_product_without_plans_is_shown_out_of_stock() -> None:
    product = Product(name="Empty", slug="empty", emoji="📦", plans=[])

    assert product.is_available is False
    assert product.button_title == "❌ Empty"
