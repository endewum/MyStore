"""Notification, stock alert and broadcast repositories."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.database.models import (
    Broadcast,
    DeliveryState,
    Notification,
    NotificationRecipient,
    StockAlert,
    StockAlertStatus,
    User,
)
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page, normalize_page
from app.utils.time import utcnow


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def paginate_for_user(
        self, user_id: int, page: int, per_page: int
    ) -> Page[NotificationRecipient]:
        stmt = (
            select(NotificationRecipient)
            .where(NotificationRecipient.user_id == user_id)
            .options(selectinload(NotificationRecipient.notification))
            .order_by(NotificationRecipient.id.desc())
        )
        total = await self.count_stmt(stmt)
        page = normalize_page(page, total, per_page)
        items = (
            await self.session.scalars(
                stmt.limit(per_page).offset((page - 1) * per_page)
            )
        ).all()
        return Page(items=list(items), page=page, per_page=per_page, total=total)

    async def count_unread(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationRecipient)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_read.is_(False),
            )
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def mark_all_read(self, user_id: int) -> None:
        await self.session.execute(
            update(NotificationRecipient)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_read.is_(False),
            )
            .values(is_read=True)
        )

    async def add_recipients(
        self, notification_id: int, user_ids: Sequence[int]
    ) -> None:
        if not user_ids:
            return
        self.session.add_all(
            [
                NotificationRecipient(notification_id=notification_id, user_id=user_id)
                for user_id in dict.fromkeys(user_ids)
            ]
        )
        await self.session.flush()

    async def mark_delivery(
        self,
        notification_id: int,
        user_id: int,
        state: DeliveryState,
        error: str | None = None,
    ) -> None:
        await self.session.execute(
            update(NotificationRecipient)
            .where(
                NotificationRecipient.notification_id == notification_id,
                NotificationRecipient.user_id == user_id,
            )
            .values(
                delivery_state=state,
                error=(error or None),
                sent_at=utcnow() if state is DeliveryState.SENT else None,
            )
        )


class StockAlertRepository(BaseRepository[StockAlert]):
    model = StockAlert

    async def get_for_user(self, plan_id: int, user_id: int) -> StockAlert | None:
        return await self.get_by(plan_id=plan_id, user_id=user_id)

    async def list_waiting(self, plan_id: int) -> Sequence[StockAlert]:
        stmt = (
            select(StockAlert)
            .where(
                StockAlert.plan_id == plan_id,
                StockAlert.status == StockAlertStatus.WAITING,
            )
            .options(selectinload(StockAlert.user))
            .order_by(StockAlert.id)
        )
        return list((await self.session.scalars(stmt)).all())

    async def count_waiting(self, plan_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(StockAlert)
            .where(
                StockAlert.plan_id == plan_id,
                StockAlert.status == StockAlertStatus.WAITING,
            )
        )
        return int((await self.session.scalar(stmt)) or 0)

    async def waiting_users(self, plan_id: int) -> Sequence[User]:
        stmt = (
            select(User)
            .join(StockAlert, StockAlert.user_id == User.id)
            .where(
                StockAlert.plan_id == plan_id,
                StockAlert.status == StockAlertStatus.WAITING,
                User.is_active.is_(True),
                User.has_blocked_bot.is_(False),
                User.is_blocked.is_(False),
            )
            .distinct()
        )
        return list((await self.session.scalars(stmt)).all())

    async def paginate_for_user(
        self, user_id: int, page: int, per_page: int
    ) -> Page[StockAlert]:
        stmt = (
            select(StockAlert)
            .where(
                StockAlert.user_id == user_id,
                StockAlert.status == StockAlertStatus.WAITING,
            )
            .options(selectinload(StockAlert.plan))
            .order_by(StockAlert.id.desc())
        )
        return await self.paginate(stmt, page, per_page)

    async def mark_notified(self, plan_id: int, user_ids: Sequence[int]) -> None:
        if not user_ids:
            return
        await self.session.execute(
            update(StockAlert)
            .where(
                StockAlert.plan_id == plan_id,
                StockAlert.user_id.in_(list(user_ids)),
                StockAlert.status == StockAlertStatus.WAITING,
            )
            .values(status=StockAlertStatus.NOTIFIED, notified_at=utcnow())
        )


class BroadcastRepository(BaseRepository[Broadcast]):
    model = Broadcast

    async def paginate_history(self, page: int, per_page: int) -> Page[Broadcast]:
        stmt = select(Broadcast).order_by(Broadcast.id.desc())
        return await self.paginate(stmt, page, per_page)
