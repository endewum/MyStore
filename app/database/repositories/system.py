"""Coupon, setting and admin-log repositories."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import select

from app.database.models import AdminAction, AdminLog, Coupon, Setting
from app.database.repositories.base import BaseRepository
from app.utils.pagination import Page


class CouponRepository(BaseRepository[Coupon]):
    model = Coupon

    async def get_by_code(self, code: str) -> Coupon | None:
        return await self.get_by(code=code.strip().upper())

    async def paginate_all(self, page: int, per_page: int) -> Page[Coupon]:
        stmt = select(Coupon).order_by(Coupon.id.desc())
        return await self.paginate(stmt, page, per_page)


class SettingRepository(BaseRepository[Setting]):
    model = Setting

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        setting = await self.get_by(key=key)
        return setting.value if setting and setting.value is not None else default

    async def set_value(
        self, key: str, value: str | None, description: str | None = None
    ) -> Setting:
        setting = await self.get_by(key=key)
        if setting is None:
            setting = Setting(key=key, value=value, description=description)
            return await self.add(setting)
        setting.value = value
        if description:
            setting.description = description
        await self.session.flush()
        return setting

    async def list_editable(self) -> Sequence[Setting]:
        stmt = (
            select(Setting).where(Setting.is_editable.is_(True)).order_by(Setting.key)
        )
        return list((await self.session.scalars(stmt)).all())


class AdminLogRepository(BaseRepository[AdminLog]):
    model = AdminLog

    async def log(
        self,
        admin_telegram_id: int,
        action: AdminAction,
        *,
        admin_username: str | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        description: str | None = None,
    ) -> AdminLog:
        return await self.add(
            AdminLog(
                admin_telegram_id=admin_telegram_id,
                admin_username=admin_username,
                action=action,
                target_type=target_type,
                target_id=target_id,
                description=description,
            )
        )

    async def paginate_recent(self, page: int, per_page: int) -> Page[AdminLog]:
        stmt = select(AdminLog).order_by(AdminLog.id.desc())
        return await self.paginate(stmt, page, per_page)
