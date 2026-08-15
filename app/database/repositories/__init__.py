"""Repository layer: the only place that builds SQL statements."""

from app.database.repositories.base import BaseRepository
from app.database.repositories.catalog import (
    CategoryRepository,
    PlanRepository,
    ProductRepository,
)
from app.database.repositories.inventory import InventoryRepository
from app.database.repositories.notification import (
    BroadcastRepository,
    NotificationRepository,
    ProductStockAlertRepository,
    StockAlertRepository,
)
from app.database.repositories.order import (
    OrderHistoryRepository,
    OrderItemRepository,
    OrderRepository,
)
from app.database.repositories.payment import (
    PaymentMethodRepository,
    PaymentRepository,
)
from app.database.repositories.system import (
    AdminLogRepository,
    CouponRepository,
    SettingRepository,
)
from app.database.repositories.user import AdminRepository, UserRepository

__all__ = [
    "AdminLogRepository",
    "AdminRepository",
    "BaseRepository",
    "BroadcastRepository",
    "CategoryRepository",
    "CouponRepository",
    "InventoryRepository",
    "NotificationRepository",
    "OrderHistoryRepository",
    "OrderItemRepository",
    "OrderRepository",
    "PaymentMethodRepository",
    "PaymentRepository",
    "PlanRepository",
    "ProductRepository",
    "ProductStockAlertRepository",
    "SettingRepository",
    "StockAlertRepository",
    "UserRepository",
]
