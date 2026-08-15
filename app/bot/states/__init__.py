"""FSM state groups."""

from app.bot.states.admin import (
    BroadcastStates,
    CategoryStates,
    CouponAdminStates,
    OrderStates,
    PaymentMethodStates,
    PaymentReviewStates,
    PlanStates,
    ProductStates,
    SettingStates,
    StockStates,
    UserAdminStates,
)
from app.bot.states.customer import (
    CouponStates,
    PaymentStates,
    SearchStates,
    SupportStates,
)

__all__ = [
    "BroadcastStates",
    "CategoryStates",
    "CouponAdminStates",
    "CouponStates",
    "OrderStates",
    "PaymentMethodStates",
    "PaymentReviewStates",
    "PaymentStates",
    "PlanStates",
    "ProductStates",
    "SearchStates",
    "SettingStates",
    "StockStates",
    "SupportStates",
    "UserAdminStates",
]
