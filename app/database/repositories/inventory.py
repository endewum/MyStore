"""Inventory repository."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select

from app.database.models import InventoryItem, InventoryStatus
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page


class InventoryRepository(BaseRepository[InventoryItem]):
    model = InventoryItem

    async def take_available(
        self, plan_id: int, quantity: int
    ) -> Sequence[InventoryItem]:
        """Fetch up to ``quantity`` available items, locking them when possible."""
        stmt = (
            select(InventoryItem)
            .where(
                InventoryItem.plan_id == plan_id,
                InventoryItem.status == InventoryStatus.AVAILABLE,
            )
            .order_by(InventoryItem.id)
            .limit(quantity)
        )
        if self.session.bind is not None and self.session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update(skip_locked=True)
        return list((await self.session.scalars(stmt)).all())

    async def list_for_order(self, order_id: int) -> Sequence[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.order_id == order_id)
            .order_by(InventoryItem.id)
        )
        return list((await self.session.scalars(stmt)).all())

    async def paginate_for_plan(
        self, plan_id: int, page: int, per_page: int
    ) -> Page[InventoryItem]:
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.plan_id == plan_id)
            .order_by(InventoryItem.status, InventoryItem.id)
        )
        return await self.paginate(stmt, page, per_page)

    async def count_by_status(self, plan_id: int, status: InventoryStatus) -> int:
        stmt = (
            select(func.count())
            .select_from(InventoryItem)
            .where(InventoryItem.plan_id == plan_id, InventoryItem.status == status)
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def status_breakdown(self, plan_id: int) -> dict[InventoryStatus, int]:
        stmt = (
            select(InventoryItem.status, func.count())
            .where(InventoryItem.plan_id == plan_id)
            .group_by(InventoryItem.status)
        )
        rows = await self.session.execute(stmt)
        breakdown = dict.fromkeys(InventoryStatus, 0)
        for status, count in rows.all():
            breakdown[InventoryStatus(status)] = int(count)
        return breakdown

    async def delete_available(self, plan_id: int, quantity: int) -> int:
        """Remove up to ``quantity`` unsold items; returns how many were removed."""
        items = await self.take_available(plan_id, quantity)
        for item in items:
            await self.session.delete(item)
        await self.session.flush()
        return len(items)

    async def exists_value(self, plan_id: int, value: str) -> bool:
        stmt = (
            select(InventoryItem.id)
            .where(InventoryItem.plan_id == plan_id, InventoryItem.value == value)
            .limit(1)
        )
        return (await self.session.scalar(stmt)) is not None
