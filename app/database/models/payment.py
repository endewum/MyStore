"""Manual payment models.

There is deliberately **no** automatic payment verification in this project:
a customer submits evidence, an administrator reviews it by hand.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import PaymentStatus
from app.database.models.types import enum_column

if TYPE_CHECKING:
    from app.database.models.order import Order
    from app.database.models.user import User


class PaymentMethod(IntPrimaryKeyMixin, TimestampMixin, Base):
    """An admin-configured manual payment channel (Binance, Bybit, USDT...).

    Credentials live in the database, never in source code, so they can be
    rotated from the admin panel without a redeploy.
    """

    __tablename__ = "payment_methods"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="💳", nullable=False)
    #: Account id / UID / wallet address shown to the customer.
    account_identifier: Mapped[Optional[str]] = mapped_column(String(255))
    #: Extra label such as the chain for crypto transfers (TRC20, BEP20...).
    network: Mapped[Optional[str]] = mapped_column(String(64))
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_screenshot: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    min_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(default=100, nullable=False, index=True)

    payments: Mapped[list["Payment"]] = relationship(back_populates="method")

    @property
    def button_title(self) -> str:
        return f"{self.emoji} {self.name}".strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.account_identifier and self.account_identifier.strip())


class Payment(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A payment attempt with customer-submitted evidence."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_status_created", "status", "created_at"),
        Index("ix_payments_order_status", "order_id", "status"),
    )

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="SET NULL"), index=True
    )
    method_code: Mapped[Optional[str]] = mapped_column(String(32))
    method_name: Mapped[Optional[str]] = mapped_column(String(80))

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    #: Free-form reference supplied by the customer (TXID, transfer note...).
    reference: Mapped[Optional[str]] = mapped_column(String(255))
    #: Telegram ``file_id`` of the proof screenshot. Files stay on Telegram's
    #: servers; the bot never writes customer uploads to local disk.
    proof_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    proof_file_unique_id: Mapped[Optional[str]] = mapped_column(String(128))
    customer_note: Mapped[Optional[str]] = mapped_column(Text)

    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    reviewed_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255))

    order: Mapped["Order"] = relationship(back_populates="payments")
    user: Mapped["User"] = relationship()
    method: Mapped[Optional["PaymentMethod"]] = relationship(back_populates="payments")

    @property
    def amount_display(self) -> str:
        return f"${self.amount:,.2f}"

    @property
    def has_evidence(self) -> bool:
        return bool(self.reference or self.proof_file_id)
