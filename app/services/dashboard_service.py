"""Aggregated statistics for the admin dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import OrderStatus
from app.database.repositories import (
    OrderRepository,
    PaymentRepository,
    PlanRepository,
    ProductRepository,
    UserRepository,
)


@dataclass(slots=True)
class DashboardStats:
    users: int
    active_users: int
    orders: int
    pending_payments: int
    completed_orders: int
    revenue: Decimal
    products: int
    plans: int
    available_plans: int
    sold_out_plans: int
    available_stock: int


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.orders = OrderRepository(session)
        self.payments = PaymentRepository(session)
        self.products = ProductRepository(session)
        self.plans = PlanRepository(session)

    async def stats(self) -> DashboardStats:
        return DashboardStats(
            users=await self.users.count(),
            active_users=await self.users.count_active(),
            orders=await self.orders.count(),
            pending_payments=await self.payments.count_pending_review(),
            completed_orders=await self.orders.count_by_status([OrderStatus.DELIVERED]),
            revenue=await self.orders.revenue(),
            products=await self.products.count(),
            plans=await self.plans.count(),
            available_plans=await self.plans.count_available(),
            sold_out_plans=await self.plans.count_sold_out(),
            available_stock=await self.plans.total_available_stock(),
        )

    async def counts(self) -> dict[str, int]:
        """Small counters used for badges in menus."""
        return {
            "pending_payments": await self.payments.count_pending_review(),
            "awaiting_fulfilment": await self.orders.count_by_status(
                [OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.READY]
            ),
        }

    async def model_counts(self) -> dict[str, int]:
        return {
            "users": await self.users.count(),
            "products": await self.products.count(),
            "plans": await self.plans.count(),
        }