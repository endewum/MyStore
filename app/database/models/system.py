"""System models: coupons, key/value settings and the admin audit log."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import AdminAction, CouponType
from app.database.models.types import enum_column
from app.utils.time import utcnow


class Coupon(IntPrimaryKeyMixin, TimestampMixin, Base):
    """Discount code applied at order confirmation time."""

    __tablename__ = "coupons"

    code: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    type: Mapped[CouponType] = mapped_column(
        enum_column(CouponType), default=CouponType.PERCENT, nullable=False
    )
    #: Percentage (0-100) when ``type`` is PERCENT, else an absolute amount.
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    min_order_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    max_uses: Mapped[int] = mapped_column(default=0, nullable=False)
    max_uses_per_user: Mapped[int] = mapped_column(default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    @property
    def is_exhausted(self) -> bool:
        return bool(self.max_uses) and self.used_count >= self.max_uses

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at < utcnow()

    @property
    def is_usable(self) -> bool:
        return self.is_active and not self.is_exhausted and not self.is_expired

    def discount_for(self, total: Decimal) -> Decimal:
        """Discount amount for ``total``, never exceeding the total itself."""
        if self.type is CouponType.PERCENT:
            amount = (total * self.value / Decimal("100")).quantize(Decimal("0.01"))
        else:
            amount = self.value
        return min(amount, total)


class Setting(IntPrimaryKeyMixin, TimestampMixin, Base):
    """Editable key/value configuration (store texts, toggles, timeouts)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdminLog(IntPrimaryKeyMixin, Base):
    """Append-only record of administrative actions."""

    __tablename__ = "admin_logs"
    __table_args__ = (
        Index("ix_admin_logs_admin_created", "admin_telegram_id", "created_at"),
        Index("ix_admin_logs_action_created", "action", "created_at"),
    )

    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    admin_username: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[AdminAction] = mapped_column(
        enum_column(AdminAction), nullable=False, index=True
    )
    target_type: Mapped[Optional[str]] = mapped_column(String(32))
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
