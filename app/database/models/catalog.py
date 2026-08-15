"""Catalog models: categories, products and plans."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.enums import DeliveryType
from app.database.models.types import enum_column

if TYPE_CHECKING:
    from app.database.models.inventory import InventoryItem
    from app.database.models.notification import StockAlert


class Category(IntPrimaryKeyMixin, TimestampMixin, Base):
    """Product grouping shown on the storefront (AI, Design, Music, ...)."""

    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    emoji: Mapped[str] = mapped_column(String(16), default="📦", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=100, nullable=False, index=True)

    products: Mapped[list["Product"]] = relationship(back_populates="category")

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}".strip()


class Product(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A store product such as ChatGPT, Canva or Netflix."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_active_sort", "is_active", "sort_order"),
        Index("ix_products_featured_sort", "is_featured", "sort_order"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    emoji: Mapped[str] = mapped_column(String(16), default="🛍", nullable=False)
    image_file_id: Mapped[Optional[str]] = mapped_column(String(255))
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=100, nullable=False)

    category: Mapped[Optional["Category"]] = relationship(back_populates="products")
    plans: Mapped[list["Plan"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Plan.sort_order",
    )

    @property
    def button_title(self) -> str:
        """Label used inside the storefront grid keyboard."""
        prefix = "🔥 " if self.is_featured else ""
        return f"{prefix}{self.name}"

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}".strip()


class Plan(IntPrimaryKeyMixin, TimestampMixin, Base):
    """A purchasable variant of a product (duration / tier / region)."""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_plans_product_id_name"),
        Index("ix_plans_product_active_sort", "product_id", "is_active", "sort_order"),
        Index("ix_plans_stock", "stock_quantity"),
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    duration: Mapped[Optional[str]] = mapped_column(String(80))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)

    stock_quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    #: Units held by orders awaiting payment/fulfilment; not sellable.
    reserved_quantity: Mapped[int] = mapped_column(default=0, nullable=False)
    sold_quantity: Mapped[int] = mapped_column(default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=100, nullable=False)
    delivery_type: Mapped[DeliveryType] = mapped_column(
        enum_column(DeliveryType), default=DeliveryType.MANUAL, nullable=False
    )
    #: Optional notes appended to the delivery message (setup steps, warranty).
    delivery_note: Mapped[Optional[str]] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="plans")
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", passive_deletes=True
    )
    stock_alerts: Mapped[list["StockAlert"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def available_quantity(self) -> int:
        """Units a customer can buy right now."""
        return max(self.stock_quantity - self.reserved_quantity, 0)

    @property
    def is_sold_out(self) -> bool:
        return self.available_quantity <= 0

    @property
    def is_purchasable(self) -> bool:
        return self.is_active and not self.is_sold_out

    @property
    def status_icon(self) -> str:
        if not self.is_active:
            return "⚫"
        return "🔴" if self.is_sold_out else "🟢"

    @property
    def price_display(self) -> str:
        return f"${self.price:,.2f}"
