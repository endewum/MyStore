"""Enumerations shared across models, services and handlers."""

from __future__ import annotations

from enum import StrEnum


class AdminRole(StrEnum):
    """Administrative roles ordered from most to least privileged."""

    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    STAFF = "STAFF"

    @property
    def level(self) -> int:
        return _ROLE_LEVELS[self]

    def covers(self, required: "AdminRole") -> bool:
        """Return True when this role satisfies ``required``."""
        return self.level >= required.level


_ROLE_LEVELS: dict[AdminRole, int] = {
    AdminRole.STAFF: 1,
    AdminRole.ADMIN: 2,
    AdminRole.SUPER_ADMIN: 3,
}


class DeliveryType(StrEnum):
    """How a purchased plan is handed over to the customer."""

    MANUAL = "MANUAL"
    CODE = "CODE"
    ACCOUNT = "ACCOUNT"
    INFORMATION = "INFORMATION"

    @property
    def label(self) -> str:
        return _DELIVERY_LABELS[self]


_DELIVERY_LABELS: dict[DeliveryType, str] = {
    DeliveryType.MANUAL: "🙋 Manual",
    DeliveryType.CODE: "🔑 Code",
    DeliveryType.ACCOUNT: "👤 Account",
    DeliveryType.INFORMATION: "📄 Information",
}


class OrderStatus(StrEnum):
    """Order lifecycle states."""

    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    PAYMENT_REJECTED = "PAYMENT_REJECTED"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    READY = "READY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"

    @property
    def label(self) -> str:
        return _ORDER_STATUS_LABELS[self]

    @property
    def is_final(self) -> bool:
        return self in {
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        }


_ORDER_STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.PENDING_PAYMENT: "⏳ Awaiting Payment",
    OrderStatus.PAYMENT_SUBMITTED: "🔎 Payment Review",
    OrderStatus.PAYMENT_REJECTED: "🚫 Payment Rejected",
    OrderStatus.PAID: "💰 Paid",
    OrderStatus.PROCESSING: "⚙️ Processing",
    OrderStatus.READY: "📦 Ready",
    OrderStatus.DELIVERED: "✅ Delivered",
    OrderStatus.CANCELLED: "❌ Cancelled",
    OrderStatus.REFUNDED: "↩️ Refunded",
}


class PaymentStatus(StrEnum):
    """Status of a manual payment submission."""

    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"

    @property
    def label(self) -> str:
        return _PAYMENT_STATUS_LABELS[self]


_PAYMENT_STATUS_LABELS: dict[PaymentStatus, str] = {
    PaymentStatus.PENDING: "⏳ Pending",
    PaymentStatus.SUBMITTED: "🔎 Under Review",
    PaymentStatus.CONFIRMED: "✅ Confirmed",
    PaymentStatus.REJECTED: "🚫 Rejected",
}


class InventoryStatus(StrEnum):
    """Status of a single inventory item."""

    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    SOLD = "SOLD"
    DISABLED = "DISABLED"

    @property
    def label(self) -> str:
        return _INVENTORY_STATUS_LABELS[self]


_INVENTORY_STATUS_LABELS: dict[InventoryStatus, str] = {
    InventoryStatus.AVAILABLE: "🟢 Available",
    InventoryStatus.RESERVED: "🟡 Reserved",
    InventoryStatus.SOLD: "🔵 Sold",
    InventoryStatus.DISABLED: "⚫ Disabled",
}


class NotificationType(StrEnum):
    """Categories of notifications persisted for users."""

    STOCK_AVAILABLE = "STOCK_AVAILABLE"
    NEW_PRODUCT = "NEW_PRODUCT"
    PRICE_CHANGE = "PRICE_CHANGE"
    PROMOTION = "PROMOTION"
    ORDER_UPDATE = "ORDER_UPDATE"
    PAYMENT_UPDATE = "PAYMENT_UPDATE"
    SYSTEM = "SYSTEM"

    @property
    def icon(self) -> str:
        return _NOTIFICATION_ICONS[self]


_NOTIFICATION_ICONS: dict[NotificationType, str] = {
    NotificationType.STOCK_AVAILABLE: "🔥",
    NotificationType.NEW_PRODUCT: "🎉",
    NotificationType.PRICE_CHANGE: "🏷",
    NotificationType.PROMOTION: "📣",
    NotificationType.ORDER_UPDATE: "📦",
    NotificationType.PAYMENT_UPDATE: "💳",
    NotificationType.SYSTEM: "ℹ️",
}


class DeliveryState(StrEnum):
    """Delivery state of a single notification recipient row."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BroadcastStatus(StrEnum):
    """Status of an admin broadcast campaign."""

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    SENDING = "SENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"

    @property
    def label(self) -> str:
        return _BROADCAST_STATUS_LABELS[self]


_BROADCAST_STATUS_LABELS: dict[BroadcastStatus, str] = {
    BroadcastStatus.DRAFT: "📝 Draft",
    BroadcastStatus.SCHEDULED: "🕒 Scheduled",
    BroadcastStatus.SENDING: "📡 Sending",
    BroadcastStatus.COMPLETED: "✅ Completed",
    BroadcastStatus.CANCELLED: "❌ Cancelled",
    BroadcastStatus.FAILED: "⚠️ Failed",
}


class BroadcastAudience(StrEnum):
    """Who should receive a broadcast."""

    ALL_USERS = "ALL_USERS"
    ACTIVE_USERS = "ACTIVE_USERS"
    CUSTOMERS = "CUSTOMERS"
    INTERESTED_USERS = "INTERESTED_USERS"

    @property
    def label(self) -> str:
        return _AUDIENCE_LABELS[self]


_AUDIENCE_LABELS: dict[BroadcastAudience, str] = {
    BroadcastAudience.ALL_USERS: "👥 All users",
    BroadcastAudience.ACTIVE_USERS: "🟢 Active users",
    BroadcastAudience.CUSTOMERS: "🧾 Past customers",
    BroadcastAudience.INTERESTED_USERS: "🔔 Waiting list",
}


class StockAlertStatus(StrEnum):
    """Status of a "Notify Me" subscription."""

    WAITING = "WAITING"
    NOTIFIED = "NOTIFIED"
    CANCELLED = "CANCELLED"


class CouponType(StrEnum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"


class AdminAction(StrEnum):
    """Auditable administrative actions."""

    ADMIN_CREATED_PRODUCT = "ADMIN_CREATED_PRODUCT"
    ADMIN_UPDATED_PRODUCT = "ADMIN_UPDATED_PRODUCT"
    ADMIN_DELETED_PRODUCT = "ADMIN_DELETED_PRODUCT"
    ADMIN_TOGGLED_PRODUCT = "ADMIN_TOGGLED_PRODUCT"
    ADMIN_CREATED_PLAN = "ADMIN_CREATED_PLAN"
    ADMIN_UPDATED_PLAN = "ADMIN_UPDATED_PLAN"
    ADMIN_DELETED_PLAN = "ADMIN_DELETED_PLAN"
    ADMIN_TOGGLED_PLAN = "ADMIN_TOGGLED_PLAN"
    ADMIN_CHANGED_PRICE = "ADMIN_CHANGED_PRICE"
    ADMIN_ADDED_STOCK = "ADMIN_ADDED_STOCK"
    ADMIN_REMOVED_STOCK = "ADMIN_REMOVED_STOCK"
    ADMIN_IMPORTED_CODES = "ADMIN_IMPORTED_CODES"
    ADMIN_CONFIRMED_PAYMENT = "ADMIN_CONFIRMED_PAYMENT"
    ADMIN_REJECTED_PAYMENT = "ADMIN_REJECTED_PAYMENT"
    ADMIN_FULFILLED_ORDER = "ADMIN_FULFILLED_ORDER"
    ADMIN_CANCELLED_ORDER = "ADMIN_CANCELLED_ORDER"
    ADMIN_REFUNDED_ORDER = "ADMIN_REFUNDED_ORDER"
    ADMIN_SENT_BROADCAST = "ADMIN_SENT_BROADCAST"
    ADMIN_SENT_STOCK_NOTIFICATION = "ADMIN_SENT_STOCK_NOTIFICATION"
    ADMIN_BLOCKED_USER = "ADMIN_BLOCKED_USER"
    ADMIN_UNBLOCKED_USER = "ADMIN_UNBLOCKED_USER"
    ADMIN_UPDATED_PAYMENT_METHOD = "ADMIN_UPDATED_PAYMENT_METHOD"
    ADMIN_UPDATED_SETTINGS = "ADMIN_UPDATED_SETTINGS"
    ADMIN_CREATED_CATEGORY = "ADMIN_CREATED_CATEGORY"
    ADMIN_UPDATED_CATEGORY = "ADMIN_UPDATED_CATEGORY"
    ADMIN_DELETED_CATEGORY = "ADMIN_DELETED_CATEGORY"
    ADMIN_CREATED_COUPON = "ADMIN_CREATED_COUPON"
    ADMIN_UPDATED_COUPON = "ADMIN_UPDATED_COUPON"
