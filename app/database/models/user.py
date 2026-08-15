"""Bot user and administrator models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import AdminRole
from app.database.models.types import enum_column

if TYPE_CHECKING:
    from app.database.models.order import Order


class User(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A Telegram user known to the bot."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_is_active_is_blocked", "is_active", "is_blocked"),
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128))
    last_name: Mapped[Optional[str]] = mapped_column(String(128))
    language_code: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Set when the bot detects the user blocked it (TelegramForbiddenError).
    has_blocked_bot: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    #: Set by an administrator to ban the user from the store.
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    block_reason: Mapped[Optional[str]] = mapped_column(String(255))

    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)

    total_orders: Mapped[int] = mapped_column(default=0, nullable=False)

    admin: Mapped[Optional["Admin"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def display_name(self) -> str:
        """Human readable name for admin screens and receipts."""
        if self.username:
            return f"@{self.username}"
        full = " ".join(filter(None, (self.first_name, self.last_name))).strip()
        return full or f"ID {self.telegram_id}"

    @property
    def full_name(self) -> str:
        return " ".join(filter(None, (self.first_name, self.last_name))).strip() or "—"

    @property
    def can_receive_messages(self) -> bool:
        return self.is_active and not self.has_blocked_bot and not self.is_blocked


class Admin(IntPrimaryKeyMixin, TimestampMixin, Base):
    """Administrative grant attached to a :class:`User`."""

    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    role: Mapped[AdminRole] = mapped_column(
        enum_column(AdminRole), default=AdminRole.ADMIN, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255))
    granted_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    last_action_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="admin")

    def has_role(self, required: AdminRole) -> bool:
        return self.is_active and self.role.covers(required)
