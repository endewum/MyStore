"""Base repository with generic CRUD and pagination helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.base import Base
from app.utils.pagination import Page, normalize_page

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin data-access layer around a single ORM model.

    Handlers never talk to repositories directly: services orchestrate them.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: int) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters).limit(1)
        return (await self.session.scalars(stmt)).first()

    async def list_all(self, **filters: Any) -> Sequence[ModelT]:
        stmt = select(self.model).filter_by(**filters)
        return (await self.session.scalars(stmt)).all()

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def create(self, **values: Any) -> ModelT:
        return await self.add(self.model(**values))

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    async def delete_by_id(self, entity_id: int) -> int:
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id)  # type: ignore[attr-defined]
        )
        await self.session.flush()
        return result.rowcount or 0

    async def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return int((await self.session.scalar(stmt)) or 0)

    async def count_stmt(self, stmt: Select[Any]) -> int:
        subquery = stmt.order_by(None).subquery()
        total = await self.session.scalar(select(func.count()).select_from(subquery))
        return int(total or 0)

    async def paginate(
        self, stmt: Select[Any], page: int, per_page: int
    ) -> Page[ModelT]:
        """Run ``stmt`` for one page, clamping out-of-range page numbers."""
        total = await self.count_stmt(stmt)
        page = normalize_page(page, total, per_page)
        offset = (page - 1) * per_page
        items = (await self.session.scalars(stmt.limit(per_page).offset(offset))).all()
        return Page(items=list(items), page=page, per_page=per_page, total=total)
