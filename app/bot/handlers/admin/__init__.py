"""Admin routers.

Every admin router applies its own :class:`~app.bot.filters.IsAdmin` filter, so
authorization cannot be bypassed by reaching a nested screen directly.
"""

from aiogram import Router

from app.bot.handlers.admin import (
    broadcasts,
    dashboard,
    inventory,
    orders,
    payments,
    plans,
    products,
    settings,
    users,
)


def build_admin_router() -> Router:
    router = Router(name="admin")
    router.include_routers(
        dashboard.router,
        products.router,
        plans.router,
        inventory.router,
        orders.router,
        payments.router,
        users.router,
        broadcasts.router,
        settings.router,
    )
    return router


__all__ = ["build_admin_router"]
