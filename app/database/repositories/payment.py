"""Payment and payment-method repositories."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database.models import Payment, PaymentMethod, PaymentStatus
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page


class PaymentMethodRepository(BaseRepository[PaymentMethod]):
    model = PaymentMethod

    async def list_enabled(self) -> Sequence[PaymentMethod]:
        stmt = (
            select(PaymentMethod)
            .where(PaymentMethod.is_enabled.is_(True))
            .order_by(PaymentMethod.sort_order, PaymentMethod.name)
        )
        methods = (await self.session.scalars(stmt)).all()
        return [method for method in methods if method.is_configured]

    async def list_all_ordered(self) -> Sequence[PaymentMethod]:
        stmt = select(PaymentMethod).order_by(
            PaymentMethod.sort_order, PaymentMethod.name
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_by_code(self, code: str) -> PaymentMethod | None:
        return await self.get_by(code=code)


class PaymentRepository(BaseRepository[Payment]):
    model = Payment

    async def get_full(self, payment_id: int) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.id == payment_id)
            .options(
                selectinload(Payment.order),
                selectinload(Payment.user),
                selectinload(Payment.method),
            )
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def latest_for_order(self, order_id: int) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def paginate_pending_review(self, page: int, per_page: int) -> Page[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.status == PaymentStatus.SUBMITTED)
            .options(selectinload(Payment.order), selectinload(Payment.user))
            .order_by(Payment.id)
        )
        return await self.paginate(stmt, page, per_page)

    async def count_pending_review(self) -> int:
        stmt = (
            select(func.count())
            .select_from(Payment)
            .where(Payment.status == PaymentStatus.SUBMITTED)
        )
        return int((await self.session.scalar(stmt)) or 0)
