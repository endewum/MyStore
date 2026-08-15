"""ORM models.

Every model is imported here so that ``Base.metadata`` is fully populated for
Alembic autogeneration and for ``create_all`` in the test suite.
"""

from app.database.models.base import Base, IntPrimaryKeyMixin, TimestampMixin
from app.database.models.catalog import Category, Plan, Product
from app.database.models.enums import (
    AdminAction,
    AdminRole,
    BroadcastAudience,
    BroadcastStatus,
    CouponType,
    DeliveryState,
    DeliveryType,
    InventoryStatus,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    StockAlertStatus,
)
from app.database.models.inventory import InventoryItem
from app.database.models.notification import (
    Broadcast,
    Notification,
    NotificationRecipient,
    ProductStockAlert,
    StockAlert,
)
from app.database.models.order import (
    ORDER_NUMBER_OFFSET,
    Order,
    OrderItem,
    OrderStatusHistory,
    format_order_number,
)
from app.database.models.payment import Payment, PaymentMethod
from app.database.models.system import AdminLog, Coupon, Setting
from app.database.models.user import Admin, User

__all__ = [
    "ORDER_NUMBER_OFFSET",
    "Admin",
    "AdminAction",
    "AdminLog",
    "AdminRole",
    "Base",
    "Broadcast",
    "BroadcastAudience",
    "BroadcastStatus",
    "Category",
    "Coupon",
    "CouponType",
    "DeliveryState",
    "DeliveryType",
    "IntPrimaryKeyMixin",
    "InventoryItem",
    "InventoryStatus",
    "Notification",
    "NotificationRecipient",
    "NotificationType",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderStatusHistory",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "Plan",
    "Product",
    "ProductStockAlert",
    "Setting",
    "StockAlert",
    "StockAlertStatus",
    "TimestampMixin",
    "User",
    "format_order_number",
]
