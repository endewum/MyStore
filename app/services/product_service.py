"""Product and category management."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin, AdminAction, Category, Product
from app.database.repositories import (
    AdminLogRepository,
    CategoryRepository,
    PlanRepository,
    ProductRepository,
)
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.pagination import Page
from app.utils.text import slugify


class ProductService:
    """Catalog reads for the storefront and writes for the admin panel."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.categories = CategoryRepository(session)
        self.plans = PlanRepository(session)
        self.logs = AdminLogRepository(session)

    # ------------------------------------------------------------ storefront
    async def storefront_page(
        self, page: int, per_page: int, category_id: int | None = None
    ) -> Page[Product]:
        return await self.products.paginate_storefront(page, per_page, category_id)

    async def get(self, product_id: int) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError("This product is no longer available.")
        return product

    async def get_visible(self, product_id: int) -> Product:
        product = await self.get(product_id)
        if not product.is_active:
            raise NotFoundError("This product is no longer available.")
        return product

    async def get_with_plans(self, product_id: int) -> Product:
        product = await self.products.get_with_plans(product_id)
        if product is None:
            raise NotFoundError("This product is no longer available.")
        return product

    async def featured(self, limit: int = 12) -> Sequence[Product]:
        return await self.products.list_featured(limit)

    async def search(self, query: str, page: int, per_page: int) -> Page[Product]:
        term = query.strip()
        if len(term) < 2:
            raise ValidationError("Please enter at least 2 characters.")
        return await self.products.search(term, page, per_page)

    # ----------------------------------------------------------- categories
    async def visible_categories(self) -> Sequence[Category]:
        return await self.categories.list_visible()

    async def all_categories(self) -> Sequence[Category]:
        return await self.categories.list_ordered()

    async def get_category(self, category_id: int) -> Category:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError("This category no longer exists.")
        return category

    async def create_category(
        self, *, name: str, emoji: str, admin: Admin | None = None
    ) -> Category:
        slug = slugify(name, "category")
        if await self.categories.get_by_slug(slug):
            raise ValidationError("A category with that name already exists.")
        category = await self.categories.create(
            name=name,
            slug=slug,
            emoji=emoji,
            sort_order=100,
        )
        await self._log(admin, AdminAction.ADMIN_CREATED_CATEGORY, category.id, name)
        return category

    async def update_category(
        self,
        category: Category,
        *,
        name: str | None = None,
        emoji: str | None = None,
        is_active: bool | None = None,
        sort_order: int | None = None,
        admin: Admin | None = None,
    ) -> Category:
        if name is not None:
            category.name = name
            category.slug = slugify(name, f"category-{category.id}")
        if emoji is not None:
            category.emoji = emoji
        if is_active is not None:
            category.is_active = is_active
        if sort_order is not None:
            category.sort_order = sort_order
        await self.session.flush()
        await self._log(
            admin, AdminAction.ADMIN_UPDATED_CATEGORY, category.id, category.name
        )
        return category

    async def delete_category(self, category: Category, admin: Admin | None = None) -> None:
        name = category.name
        category_id = category.id
        await self.categories.delete(category)
        await self._log(admin, AdminAction.ADMIN_DELETED_CATEGORY, category_id, name)

    # -------------------------------------------------------------- products
    async def admin_page(self, page: int, per_page: int) -> Page[Product]:
        return await self.products.paginate_admin(page, per_page)

    async def create_product(
        self,
        *,
        name: str,
        description: str | None,
        emoji: str,
        category_id: int | None,
        is_featured: bool = False,
        image_file_id: str | None = None,
        admin: Admin | None = None,
    ) -> Product:
        base_slug = slugify(name, "product")
        slug = base_slug
        suffix = 2
        while await self.products.slug_exists(slug):
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        product = await self.products.create(
            name=name,
            slug=slug,
            description=description,
            emoji=emoji,
            category_id=category_id,
            is_featured=is_featured,
            image_file_id=image_file_id,
            sort_order=await self.products.next_sort_order(),
        )
        await self._log(admin, AdminAction.ADMIN_CREATED_PRODUCT, product.id, name)
        return product

    async def update_product(
        self,
        product: Product,
        *,
        admin: Admin | None = None,
        **fields: object,
    ) -> Product:
        allowed = {
            "name",
            "description",
            "emoji",
            "category_id",
            "is_active",
            "is_featured",
            "sort_order",
            "image_file_id",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field: {', '.join(sorted(unknown))}")
        for key, value in fields.items():
            setattr(product, key, value)
        if "name" in fields:
            product.slug = slugify(str(fields["name"]), f"product-{product.id}")
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_UPDATED_PRODUCT,
            product.id,
            f"{product.name}: {', '.join(sorted(fields))}",
        )
        return product

    async def toggle_product(
        self, product: Product, admin: Admin | None = None
    ) -> Product:
        product.is_active = not product.is_active
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_TOGGLED_PRODUCT,
            product.id,
            f"{product.name} -> {'active' if product.is_active else 'inactive'}",
        )
        return product

    async def toggle_featured(
        self, product: Product, admin: Admin | None = None
    ) -> Product:
        product.is_featured = not product.is_featured
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_UPDATED_PRODUCT,
            product.id,
            f"{product.name} featured={product.is_featured}",
        )
        return product

    async def move_product(
        self, product: Product, direction: int, admin: Admin | None = None
    ) -> Product:
        """Shift a product up (-1) or down (+1) in the storefront ordering."""
        product.sort_order = max(product.sort_order + direction * 15, 0)
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_UPDATED_PRODUCT,
            product.id,
            f"{product.name} sort_order={product.sort_order}",
        )
        return product

    async def delete_product(self, product: Product, admin: Admin | None = None) -> None:
        name, product_id = product.name, product.id
        await self.products.delete(product)
        await self._log(admin, AdminAction.ADMIN_DELETED_PRODUCT, product_id, name)

    async def _log(
        self,
        admin: Admin | None,
        action: AdminAction,
        target_id: int | None,
        description: str | None,
    ) -> None:
        if admin is None:
            return
        await self.logs.log(
            admin.telegram_id,
            action,
            admin_username=admin.username,
            target_type="product",
            target_id=target_id,
            description=description,
        )
