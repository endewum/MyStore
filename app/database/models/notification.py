"""Notification, stock alert and broadcast models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import (
    BroadcastAudience,
    BroadcastStatus,
    DeliveryState,
    NotificationType,
    StockAlertStatus,
)
from app.database.models.types import enum_column
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.database.models.catalog import Plan, Product
    from app.database.models.user import User


class Notification(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A notification payload that may fan out to many recipients."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_type_created", "type", "created_at"),)

    type: Mapped[NotificationType] = mapped_column(
        enum_column(NotificationType), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    created_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    #: True when the notification was also pushed out as a Telegram message.
    is_broadcast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    recipients: Mapped[list["NotificationRecipient"]] = relationship(
        back_populates="notification",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class NotificationRecipient(IntPrimaryKeyMixin, Base):
    """Per-user delivery row for a :class:`Notification`."""

    __tablename__ = "notification_recipients"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "user_id", name="uq_notification_recipients_pair"
        ),
        Index("ix_notification_recipients_user_read", "user_id", "is_read"),
    )

    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delivery_state: Mapped[DeliveryState] = mapped_column(
        enum_column(DeliveryState), default=DeliveryState.PENDING, nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(String(255))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    notification: Mapped["Notification"] = relationship(back_populates="recipients")
    user: Mapped["User"] = relationship()


class StockAlert(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A "🔔 Notify Me" subscription for a sold-out plan."""

    __tablename__ = "stock_alerts"
    __table_args__ = (
        UniqueConstraint("plan_id", "user_id", name="uq_stock_alerts_plan_user"),
        Index("ix_stock_alerts_plan_status", "plan_id", "status"),
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[StockAlertStatus] = mapped_column(
        enum_column(StockAlertStatus),
        default=StockAlertStatus.WAITING,
        nullable=False,
        index=True,
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    plan: Mapped["Plan"] = relationship(back_populates="stock_alerts")
    user: Mapped["User"] = relationship()


class ProductStockAlert(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A product-level waiting-list entry for products with no live plans.

    Plan-level alerts are more precise once a product has offers. This separate
    row lets a customer request a notification even when an admin has created
    only the product shell and has not added the first plan yet.
    """

    __tablename__ = "product_stock_alerts"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "user_id",
            name="uq_product_stock_alerts_product_user",
        ),
        Index("ix_product_stock_alerts_product_status", "product_id", "status"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[StockAlertStatus] = mapped_column(
        enum_column(StockAlertStatus),
        default=StockAlertStatus.WAITING,
        nullable=False,
        index=True,
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    product: Mapped["Product"] = relationship()
    user: Mapped["User"] = relationship()


class Broadcast(IntPrimaryKeyMixin, TimestampMixin, Base):
    """An admin broadcast campaign with delivery statistics."""

    __tablename__ = "broadcasts"
    __table_args__ = (Index("ix_broadcasts_status_created", "status", "created_at"),)

    title: Mapped[Optional[str]] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    #: Optional deep-link button, e.g. a plan the campaign advertises.
    button_text: Mapped[Optional[str]] = mapped_column(String(64))
    button_callback: Mapped[Optional[str]] = mapped_column(String(64))

    audience: Mapped[BroadcastAudience] = mapped_column(
        enum_column(BroadcastAudience),
        default=BroadcastAudience.ACTIVE_USERS,
        nullable=False,
    )
    status: Mapped[BroadcastStatus] = mapped_column(
        enum_column(BroadcastStatus),
        default=BroadcastStatus.DRAFT,
        nullable=False,
        index=True,
    )
    plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL")
    )

    total_recipients: Mapped[int] = mapped_column(default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(default=0, nullable=False)
    #: Telegram IDs that failed, kept for later cleanup of dead chats.
    failed_telegram_ids: Mapped[Optional[str]] = mapped_column(Text)

    created_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    @property
    def progress_percent(self) -> int:
        if not self.total_recipients:
            return 0
        done = self.sent_count + self.failed_count
        return min(int(done * 100 / self.total_recipients), 100)
