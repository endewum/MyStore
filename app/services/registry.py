"""Per-update service container.

The middleware builds one :class:`Services` object per Telegram update and puts
it in the handler data, so handlers only ever talk to services (never to
repositories or raw SQL).
"""

from __future__ import annotations

from functools import cached_property

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services.broadcast_service import BroadcastService
from app.services.dashboard_service import DashboardService
from app.services.delivery import MessageDispatcher
from app.services.inventory_service import InventoryService
from app.services.notification_service import NotificationService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentService
from app.services.plan_service import PlanService
from app.services.product_service import ProductService
from app.services.settings_service import SettingsService
from app.services.user_service import UserService


class Services:
    """Lazily instantiated services sharing a single database session."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        bot: Bot | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.bot = bot

    @cached_property
    def dispatcher(self) -> MessageDispatcher | None:
        """Outbound messenger used for notifications and broadcasts."""
        if self.bot is None:
            return None
        return MessageDispatcher(
            self.bot,
            messages_per_second=self.settings.store.broadcast_messages_per_second,
            on_blocked=self.users.mark_bot_blocked,
        )

    @cached_property
    def users(self) -> UserService:
        return UserService(self.session)

    @cached_property
    def products(self) -> ProductService:
        return ProductService(self.session)

    @cached_property
    def plans(self) -> PlanService:
        return PlanService(self.session)

    @cached_property
    def inventory(self) -> InventoryService:
        return InventoryService(self.session)

    @cached_property
    def orders(self) -> OrderService:
        return OrderService(self.session, self.settings.store)

    @cached_property
    def payments(self) -> PaymentService:
        return PaymentService(self.session, self.settings.store, self.orders)

    @cached_property
    def notifications(self) -> NotificationService:
        return NotificationService(self.session, self.dispatcher)

    @cached_property
    def broadcasts(self) -> BroadcastService:
        return BroadcastService(self.session, self.dispatcher)

    @cached_property
    def dashboard(self) -> DashboardService:
        return DashboardService(self.session)

    @cached_property
    def store_settings(self) -> SettingsService:
        return SettingsService(self.session)
