"""Handler routers and their registration order.

Admin routers come first so admin callbacks are matched before the customer
ones; the fallback router is last so unknown input still gets a reply.
"""

from aiogram import Router

from app.bot.handlers import (
    account,
    fallback,
    notifications,
    orders,
    payments,
    plans,
    products,
    start,
    store,
)
from app.bot.handlers.admin import build_admin_router


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(build_admin_router())
    router.include_routers(
        start.router,
        store.router,
        products.router,
        plans.router,
        orders.router,
        payments.router,
        account.router,
        notifications.router,
        fallback.router,
    )
    return router


__all__ = ["build_router"]
