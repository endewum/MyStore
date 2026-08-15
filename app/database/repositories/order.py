"""Order repositories."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database.models import (
    ORDER_NUMBER_OFFSET,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
)
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page

_LOADERS = (
    selectinload(Order.items),
    selectinload(Order.payments),
    selectinload(Order.user),
)


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def get_full(self, order_id: int) -> Order | None:
        stmt = select(Order).where(Order.id == order_id).options(*_LOADERS).limit(1)
        return (await self.session.scalars(stmt)).first()

    async def get_by_number(self, order_number: str) -> Order | None:
        stmt = (
            select(Order)
            .where(Order.order_number == order_number)
            .options(*_LOADERS)
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def next_order_number(self) -> str:
        """Sequential, human friendly order number starting at #10001."""
        current = await self.session.scalar(select(func.max(Order.id)))
        return str(int(current or 0) + 1 + ORDER_NUMBER_OFFSET)

    async def paginate_for_user(
        self, user_id: int, page: int, per_page: int
    ) -> Page[Order]:
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .options(selectinload(Order.items))
            .order_by(Order.id.desc())
        )
        return await self.paginate(stmt, page, per_page)

    async def paginate_by_status(
        self, statuses: Sequence[OrderStatus] | None, page: int, per_page: int
    ) -> Page[Order]:
        stmt = select(Order).options(*_LOADERS).order_by(Order.id.desc())
        if statuses:
            stmt = stmt.where(Order.status.in_(list(statuses)))
        return await self.paginate(stmt, page, per_page)

    async def count_by_status(self, statuses: Sequence[OrderStatus]) -> int:
        stmt = (
            select(func.count())
            .select_from(Order)
            .where(Order.status.in_(list(statuses)))
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def revenue(self) -> Decimal:
        """Sum of orders whose payment was confirmed."""
        stmt = select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.status.in_(
                [
                    OrderStatus.PAID,
                    OrderStatus.PROCESSING,
                    OrderStatus.READY,
                    OrderStatus.DELIVERED,
                ]
            )
        )
        return Decimal(str(await self.session.scalar(stmt) or "0"))

    async def list_expired_pending(self, limit: int = 50) -> Sequence[Order]:
        from app.utils.time import utcnow

        stmt = (
            select(Order)
            .where(
                Order.status == OrderStatus.PENDING_PAYMENT,
                Order.expires_at.is_not(None),
                Order.expires_at < utcnow(),
            )
            .options(selectinload(Order.items))
            .order_by(Order.id)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def has_delivered_order(self, user_id: int) -> bool:
        stmt = (
            select(Order.id)
            .where(Order.user_id == user_id, Order.status == OrderStatus.DELIVERED)
            .limit(1)
        )
        return (await self.session.scalar(stmt)) is not None


class OrderItemRepository(BaseRepository[OrderItem]):
    model = OrderItem


class OrderHistoryRepository(BaseRepository[OrderStatusHistory]):
    model = OrderStatusHistory

    async def list_for_order(self, order_id: int) -> Sequence[OrderStatusHistory]:
        stmt = (
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.id)
        )
        return list((await self.session.scalars(stmt)).all())
