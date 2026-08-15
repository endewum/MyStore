"""User and admin repositories."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.database.models import Admin, AdminRole, Order, OrderStatus, User
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.admin))
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def search(self, query: str, page: int, per_page: int) -> Page[User]:
        pattern = f"%{query.strip().lstrip('@')}%"
        stmt = select(User).order_by(User.id.desc())
        if query.strip().isdigit():
            stmt = stmt.where(User.telegram_id == int(query.strip()))
        else:
            stmt = stmt.where(
                or_(
                    User.username.ilike(pattern),
                    User.first_name.ilike(pattern),
                    User.last_name.ilike(pattern),
                )
            )
        return await self.paginate(stmt, page, per_page)

    async def paginate_users(self, page: int, per_page: int) -> Page[User]:
        stmt = select(User).order_by(User.id.desc())
        return await self.paginate(stmt, page, per_page)

    async def touch_activity(self, user_id: int, moment: datetime) -> None:
        await self.session.execute(
            update(User).where(User.id == user_id).values(last_activity_at=moment)
        )

    async def mark_bot_blocked(self, telegram_id: int, blocked: bool = True) -> None:
        """Flag a chat the bot can no longer write to, so broadcasts skip it."""
        await self.session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(has_blocked_bot=blocked, is_active=not blocked)
        )

    def _broadcastable(self) -> Select[tuple[User]]:
        return select(User).where(
            User.is_active.is_(True),
            User.has_blocked_bot.is_(False),
            User.is_blocked.is_(False),
        )

    async def all_telegram_ids(self, only_active: bool = True) -> Sequence[int]:
        stmt = self._broadcastable() if only_active else select(User)
        rows = await self.session.scalars(stmt.with_only_columns(User.telegram_id))
        return list(rows.all())

    async def broadcast_audience(self, only_active: bool = True) -> Sequence[User]:
        stmt = self._broadcastable() if only_active else select(User)
        return list((await self.session.scalars(stmt)).all())

    async def customers(self) -> Sequence[User]:
        """Users with at least one delivered order."""
        stmt = (
            self._broadcastable()
            .join(Order, Order.user_id == User.id)
            .where(Order.status == OrderStatus.DELIVERED)
            .distinct()
        )
        return list((await self.session.scalars(stmt)).all())

    async def notifiable(self) -> Sequence[User]:
        stmt = self._broadcastable().where(User.notifications_enabled.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def count_active(self) -> int:
        return int(
            (
                await self.session.scalar(
                    select(func.count()).select_from(self._broadcastable().subquery())
                )
            )
            or 0
        )


class AdminRepository(BaseRepository[Admin]):
    model = Admin

    async def get_by_telegram_id(self, telegram_id: int) -> Admin | None:
        stmt = (
            select(Admin)
            .where(Admin.telegram_id == telegram_id)
            .options(selectinload(Admin.user))
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def list_active(self) -> Sequence[Admin]:
        stmt = (
            select(Admin)
            .where(Admin.is_active.is_(True))
            .options(selectinload(Admin.user))
            .order_by(Admin.role, Admin.id)
        )
        return list((await self.session.scalars(stmt)).all())

    async def list_by_role(self, role: AdminRole) -> Sequence[Admin]:
        stmt = select(Admin).where(Admin.is_active.is_(True), Admin.role == role)
        return list((await self.session.scalars(stmt)).all())
