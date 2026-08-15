"""Plan management (the purchasable variants of a product)."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin, AdminAction, DeliveryType, Plan
from app.database.repositories import (
    AdminLogRepository,
    InventoryRepository,
    PlanRepository,
    ProductRepository,
    StockAlertRepository,
)
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.pagination import Page


class PlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans = PlanRepository(session)
        self.products = ProductRepository(session)
        self.items = InventoryRepository(session)
        self.alerts = StockAlertRepository(session)
        self.logs = AdminLogRepository(session)

    async def get(self, plan_id: int) -> Plan:
        plan = await self.plans.get_with_product(plan_id)
        if plan is None:
            raise NotFoundError("This plan no longer exists.")
        return plan

    async def get_purchasable(self, plan_id: int) -> Plan:
        """Fetch a plan that a customer is allowed to check out right now."""
        plan = await self.get(plan_id)
        if not plan.is_active or not plan.product.is_active:
            raise NotFoundError("This plan is not on sale right now.")
        return plan

    async def storefront_page(
        self, product_id: int, page: int, per_page: int
    ) -> Page[Plan]:
        return await self.plans.paginate_for_product(product_id, page, per_page)

    async def admin_page(self, product_id: int, page: int, per_page: int) -> Page[Plan]:
        return await self.plans.paginate_admin(product_id, page, per_page)

    async def list_for_product(self, product_id: int) -> Sequence[Plan]:
        return await self.plans.list_for_product(product_id)

    async def create_plan(
        self,
        *,
        product_id: int,
        name: str,
        price: Decimal,
        duration: str | None = None,
        description: str | None = None,
        delivery_type: DeliveryType = DeliveryType.MANUAL,
        stock_quantity: int = 0,
        currency: str = "USD",
        is_featured: bool = False,
        admin: Admin | None = None,
    ) -> Plan:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError("This product no longer exists.")
        duplicate = await self.plans.get_by(product_id=product_id, name=name)
        if duplicate is not None:
            raise ValidationError("This product already has a plan with that name.")
        plan = await self.plans.create(
            product_id=product_id,
            name=name,
            price=price,
            duration=duration,
            description=description,
            delivery_type=delivery_type,
            stock_quantity=max(stock_quantity, 0),
            currency=currency,
            is_featured=is_featured,
            sort_order=await self.plans.next_sort_order(product_id),
        )
        await self._log(
            admin,
            AdminAction.ADMIN_CREATED_PLAN,
            plan,
            f"{product.name} / {name} @ {price}",
        )
        return plan

    async def update_plan(
        self, plan: Plan, *, admin: Admin | None = None, **fields: object
    ) -> Plan:
        allowed = {
            "name",
            "description",
            "duration",
            "delivery_type",
            "delivery_note",
            "is_active",
            "is_featured",
            "sort_order",
            "currency",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValidationError(f"Unsupported field: {', '.join(sorted(unknown))}")
        if "name" in fields:
            duplicate = await self.plans.get_by(
                product_id=plan.product_id, name=str(fields["name"])
            )
            if duplicate is not None and duplicate.id != plan.id:
                raise ValidationError("Another plan already uses that name.")
        for key, value in fields.items():
            setattr(plan, key, value)
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_UPDATED_PLAN,
            plan,
            f"updated {', '.join(sorted(fields))}",
        )
        return plan

    async def change_price(
        self, plan: Plan, price: Decimal, *, admin: Admin | None = None
    ) -> tuple[Plan, Decimal]:
        """Update a price and return the previous value for notifications."""
        if price < 0:
            raise ValidationError("Price cannot be negative.")
        previous = plan.price
        plan.price = price
        await self.session.flush()
        await self._log(
            admin, AdminAction.ADMIN_CHANGED_PRICE, plan, f"{previous} -> {price}"
        )
        return plan, previous

    async def toggle_active(self, plan: Plan, *, admin: Admin | None = None) -> Plan:
        plan.is_active = not plan.is_active
        await self.session.flush()
        await self._log(
            admin,
            AdminAction.ADMIN_TOGGLED_PLAN,
            plan,
            "enabled" if plan.is_active else "disabled",
        )
        return plan

    async def toggle_featured(self, plan: Plan, *, admin: Admin | None = None) -> Plan:
        plan.is_featured = not plan.is_featured
        await self.session.flush()
        await self._log(
            admin, AdminAction.ADMIN_UPDATED_PLAN, plan, f"featured={plan.is_featured}"
        )
        return plan

    async def move(self, plan: Plan, direction: int, *, admin: Admin | None = None) -> Plan:
        plan.sort_order = max(plan.sort_order + direction * 15, 0)
        await self.session.flush()
        return plan

    async def delete_plan(self, plan: Plan, *, admin: Admin | None = None) -> None:
        if plan.reserved_quantity > 0:
            raise ValidationError(
                "This plan has open orders holding stock. Resolve them first."
            )
        name, plan_id = plan.name, plan.id
        await self.plans.delete(plan)
        if admin is not None:
            await self.logs.log(
                admin.telegram_id,
                AdminAction.ADMIN_DELETED_PLAN,
                admin_username=admin.user.username if admin.user else None,
                target_type="plan",
                target_id=plan_id,
                description=name,
            )

    async def waiting_count(self, plan_id: int) -> int:
        return await self.alerts.count_waiting(plan_id)

    async def _log(
        self, admin: Admin | None, action: AdminAction, plan: Plan, description: str
    ) -> None:
        if admin is None:
            return
        await self.logs.log(
            admin.telegram_id,
            action,
            admin_username=admin.user.username if admin.user else None,
            target_type="plan",
            target_id=plan.id,
            description=description,
        )
