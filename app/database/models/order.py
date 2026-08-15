"""Order, order item and status history models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import OrderStatus
from app.database.models.types import enum_column
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.database.models.catalog import Plan, Product
    from app.database.models.inventory import InventoryItem
    from app.database.models.payment import Payment
    from app.database.models.user import User

#: Customer facing order numbers start here so they never look like "#1".
ORDER_NUMBER_OFFSET = 10_000


def format_order_number(order_id: int) -> str:
    """Customer facing number for an order.

    Derived from the primary key so it is unique even when several customers
    check out at the same moment.
    """
    return str(order_id + ORDER_NUMBER_OFFSET)


class Order(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A customer order. One order currently carries a single plan."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_status", "user_id", "status"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    order_number: Mapped[str] = mapped_column(
        String(24), unique=True, nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        enum_column(OrderStatus),
        default=OrderStatus.PENDING_PAYMENT,
        nullable=False,
        index=True,
    )

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)

    coupon_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("coupons.id", ondelete="SET NULL")
    )
    coupon_code: Mapped[Optional[str]] = mapped_column(String(48))

    #: Delivery payload written by the admin during fulfilment.
    delivery_content: Mapped[Optional[str]] = mapped_column(Text)
    admin_note: Mapped[Optional[str]] = mapped_column(Text)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(255))

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    #: Whether the reserved stock has already been consumed or released.
    stock_settled: Mapped[bool] = mapped_column(default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Payment.id",
    )
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="order"
    )
    history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OrderStatusHistory.id",
    )

    @property
    def item(self) -> Optional["OrderItem"]:
        """Primary (currently only) line item of the order."""
        return self.items[0] if self.items else None

    @property
    def latest_payment(self) -> Optional["Payment"]:
        return self.payments[-1] if self.payments else None

    @property
    def total_display(self) -> str:
        return f"${self.total:,.2f}"


class OrderItem(IntPrimaryKeyMixin, TimestampMixin, Base):
    """Snapshot of the purchased plan, kept immutable for order history."""

    __tablename__ = "order_items"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(120), nullable=False)
    plan_name: Mapped[str] = mapped_column(String(160), nullable=False)
    duration: Mapped[Optional[str]] = mapped_column(String(80))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(default=1, nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(32), default="MANUAL")

    order: Mapped["Order"] = relationship(back_populates="items")
    plan: Mapped[Optional["Plan"]] = relationship()
    product: Mapped[Optional["Product"]] = relationship()

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class OrderStatusHistory(IntPrimaryKeyMixin, Base):
    """Append-only audit trail of order state transitions."""

    __tablename__ = "order_status_history"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[OrderStatus]] = mapped_column(enum_column(OrderStatus))
    to_status: Mapped[OrderStatus] = mapped_column(
        enum_column(OrderStatus), nullable=False
    )
    changed_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    order: Mapped["Order"] = relationship(back_populates="history")
