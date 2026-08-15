"""Inventory items backing CODE/ACCOUNT style plans."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import InventoryStatus
from app.database.models.types import enum_column

if TYPE_CHECKING:
    from app.database.models.catalog import Plan
    from app.database.models.order import Order


class InventoryItem(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A single deliverable unit (licence key, account credentials, ...).

    Item ``value`` is never exposed to a customer before the related order
    reaches a paid + fulfilled state; see ``InventoryService``.
    """

    __tablename__ = "inventory"
    __table_args__ = (
        Index("ix_inventory_plan_status", "plan_id", "status"),
        Index("ix_inventory_order", "order_id"),
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[InventoryStatus] = mapped_column(
        enum_column(InventoryStatus),
        default=InventoryStatus.AVAILABLE,
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL")
    )
    reserved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    added_by_telegram_id: Mapped[Optional[int]] = mapped_column()

    plan: Mapped["Plan"] = relationship(back_populates="inventory_items")
    order: Mapped[Optional["Order"]] = relationship(back_populates="inventory_items")

    @property
    def masked_value(self) -> str:
        """Partially hidden value, safe to show on admin list screens."""
        value = self.value.strip()
        if len(value) <= 6:
            return "•" * len(value)
        return f"{value[:3]}{'•' * 6}{value[-3:]}"
