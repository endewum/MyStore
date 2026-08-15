"""Category, product and plan repositories."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.database.models import Category, Plan, Product
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page


class CategoryRepository(BaseRepository[Category]):
    model = Category

    async def list_visible(self) -> Sequence[Category]:
        stmt = (
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_ordered(self) -> Sequence[Category]:
        """All categories with their products loaded, for admin screens."""
        stmt = (
            select(Category)
            .options(selectinload(Category.products))
            .order_by(Category.sort_order, Category.name)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_by_slug(self, slug: str) -> Category | None:
        return await self.get_by(slug=slug)


class ProductRepository(BaseRepository[Product]):
    model = Product

    def _storefront_stmt(self, category_id: int | None = None) -> Select[tuple[Product]]:
        """Active products, featured first, then by sort order and name."""
        stmt = select(Product).where(Product.is_active.is_(True))
        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        return stmt.order_by(
            Product.is_featured.desc(), Product.sort_order, Product.name
        )

    async def paginate_storefront(
        self, page: int, per_page: int, category_id: int | None = None
    ) -> Page[Product]:
        return await self.paginate(self._storefront_stmt(category_id), page, per_page)

    async def paginate_admin(self, page: int, per_page: int) -> Page[Product]:
        stmt = select(Product).order_by(Product.sort_order, Product.name)
        return await self.paginate(stmt, page, per_page)

    async def get_with_plans(self, product_id: int) -> Product | None:
        stmt = (
            select(Product)
            .where(Product.id == product_id)
            .options(selectinload(Product.plans), selectinload(Product.category))
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def list_featured(self, limit: int = 12) -> Sequence[Product]:
        stmt = (
            select(Product)
            .where(Product.is_active.is_(True), Product.is_featured.is_(True))
            .order_by(Product.sort_order, Product.name)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def search(self, query: str, page: int, per_page: int) -> Page[Product]:
        """Match a product by its own name, its category, or any plan name."""
        pattern = f"%{query.strip()}%"
        plan_match = (
            select(Plan.product_id)
            .where(Plan.is_active.is_(True), Plan.name.ilike(pattern))
            .scalar_subquery()
        )
        category_match = (
            select(Category.id).where(Category.name.ilike(pattern)).scalar_subquery()
        )
        stmt = (
            select(Product)
            .where(
                Product.is_active.is_(True),
                or_(
                    Product.name.ilike(pattern),
                    Product.description.ilike(pattern),
                    Product.id.in_(plan_match),
                    Product.category_id.in_(category_match),
                ),
            )
            .order_by(Product.is_featured.desc(), Product.name)
        )
        return await self.paginate(stmt, page, per_page)

    async def next_sort_order(self) -> int:
        current = await self.session.scalar(select(func.max(Product.sort_order)))
        return int(current or 0) + 10

    async def slug_exists(self, slug: str) -> bool:
        return await self.get_by(slug=slug) is not None


class PlanRepository(BaseRepository[Plan]):
    model = Plan

    async def get_with_product(self, plan_id: int) -> Plan | None:
        stmt = (
            select(Plan)
            .where(Plan.id == plan_id)
            .options(selectinload(Plan.product))
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def get_for_update(self, plan_id: int) -> Plan | None:
        """Row-locked read used when reserving stock.

        ``SELECT ... FOR UPDATE`` serialises concurrent buyers on MySQL. SQLite
        has no row locks, so ``with_for_update`` is skipped there (tests run
        single-connection anyway).
        """
        stmt = select(Plan).where(Plan.id == plan_id).limit(1)
        if self.session.bind is not None and self.session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        return (await self.session.scalars(stmt)).first()

    def _visible_stmt(self, product_id: int) -> Select[tuple[Plan]]:
        return (
            select(Plan)
            .where(Plan.product_id == product_id, Plan.is_active.is_(True))
            .order_by(Plan.is_featured.desc(), Plan.sort_order, Plan.name)
        )

    async def paginate_for_product(
        self, product_id: int, page: int, per_page: int
    ) -> Page[Plan]:
        return await self.paginate(self._visible_stmt(product_id), page, per_page)

    async def paginate_admin(
        self, product_id: int, page: int, per_page: int
    ) -> Page[Plan]:
        stmt = (
            select(Plan)
            .where(Plan.product_id == product_id)
            .order_by(Plan.sort_order, Plan.name)
        )
        return await self.paginate(stmt, page, per_page)

    async def list_for_product(self, product_id: int) -> Sequence[Plan]:
        return list((await self.session.scalars(self._visible_stmt(product_id))).all())

    async def count_available(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Plan)
            .where(
                Plan.is_active.is_(True),
                Plan.stock_quantity - Plan.reserved_quantity > 0,
            )
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def count_sold_out(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Plan)
            .where(
                Plan.is_active.is_(True),
                Plan.stock_quantity - Plan.reserved_quantity <= 0,
            )
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def next_sort_order(self, product_id: int) -> int:
        current = await self.session.scalar(
            select(func.max(Plan.sort_order)).where(Plan.product_id == product_id)
        )
        return int(current or 0) + 10

    async def paginate_low_stock(
        self, page: int, per_page: int, threshold: int = 0
    ) -> Page[Plan]:
        stmt = (
            select(Plan)
            .where(
                Plan.is_active.is_(True),
                Plan.stock_quantity - Plan.reserved_quantity <= threshold,
            )
            .options(selectinload(Plan.product))
            .order_by(Plan.product_id, Plan.sort_order)
        )
        return await self.paginate(stmt, page, per_page)

    async def total_available_stock(self) -> int:
        stmt = select(func.coalesce(func.sum(Plan.stock_quantity), 0)).where(
            Plan.is_active.is_(True)
        )
        return int((await self.session.scalar(stmt)) or 0)
