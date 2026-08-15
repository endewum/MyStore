"""Notification service.

Notifications are always persisted first (so users can re-read them under
🔔 Notifications) and only then pushed to Telegram. Push delivery goes through
:class:`~app.services.delivery.MessageDispatcher`, which absorbs per-user
failures and respects flood limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Admin,
    AdminAction,
    DeliveryState,
    Notification,
    NotificationRecipient,
    NotificationType,
    Plan,
    StockAlert,
    StockAlertStatus,
    User,
)
from app.database.repositories import (
    AdminLogRepository,
    NotificationRepository,
    StockAlertRepository,
    UserRepository,
)
from app.services.delivery import MessageDispatcher
from app.services.exceptions import ValidationError
from app.utils.logging import get_logger
from app.utils.pagination import Page

logger = get_logger(__name__)


@dataclass(slots=True)
class PushReport:
    """Delivery statistics for one push."""

    notification_id: int | None = None
    total: int = 0
    sent: int = 0
    failed: int = 0
    failed_telegram_ids: list[int] = field(default_factory=list)

    @property
    def progress_percent(self) -> int:
        if not self.total:
            return 100
        return min(int((self.sent + self.failed) * 100 / self.total), 100)


class NotificationService:
    def __init__(
        self, session: AsyncSession, dispatcher: MessageDispatcher | None = None
    ) -> None:
        self.session = session
        self.dispatcher = dispatcher
        self.notifications = NotificationRepository(session)
        self.alerts = StockAlertRepository(session)
        self.users = UserRepository(session)
        self.logs = AdminLogRepository(session)

    # ------------------------------------------------------------ user inbox
    async def inbox(
        self, user: User, page: int, per_page: int
    ) -> Page[NotificationRecipient]:
        return await self.notifications.paginate_for_user(user.id, page, per_page)

    async def unread_count(self, user: User) -> int:
        return await self.notifications.count_unread(user.id)

    async def mark_all_read(self, user: User) -> None:
        await self.notifications.mark_all_read(user.id)

    # ----------------------------------------------------------- persistence
    async def record(
        self,
        *,
        type: NotificationType,
        title: str,
        body: str,
        recipients: Sequence[User],
        plan_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        created_by_telegram_id: int | None = None,
        is_broadcast: bool = False,
    ) -> Notification:
        """Persist a notification and its per-user delivery rows."""
        notification = await self.notifications.create(
            type=type,
            title=title,
            body=body,
            plan_id=plan_id,
            product_id=product_id,
            order_id=order_id,
            created_by_telegram_id=created_by_telegram_id,
            is_broadcast=is_broadcast,
        )
        await self.notifications.add_recipients(
            notification.id, [user.id for user in recipients]
        )
        return notification

    async def push(
        self,
        *,
        type: NotificationType,
        title: str,
        body: str,
        recipients: Sequence[User],
        message_text: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        photo_file_id: str | None = None,
        plan_id: int | None = None,
        product_id: int | None = None,
        order_id: int | None = None,
        created_by_telegram_id: int | None = None,
        is_broadcast: bool = False,
    ) -> PushReport:
        """Persist a notification and deliver it to every eligible recipient."""
        eligible = [user for user in recipients if user.can_receive_messages]
        notification = await self.record(
            type=type,
            title=title,
            body=body,
            recipients=eligible,
            plan_id=plan_id,
            product_id=product_id,
            order_id=order_id,
            created_by_telegram_id=created_by_telegram_id,
            is_broadcast=is_broadcast,
        )
        report = PushReport(notification_id=notification.id, total=len(eligible))
        if self.dispatcher is None or not eligible:
            return report

        text = message_text or f"{title}\n\n{body}"
        for user in eligible:
            result = await self.dispatcher.send(
                user.telegram_id,
                text,
                reply_markup=reply_markup,
                photo_file_id=photo_file_id,
                disable_notification=is_broadcast,
            )
            if result.ok:
                report.sent += 1
                await self.notifications.mark_delivery(
                    notification.id, user.id, DeliveryState.SENT
                )
            else:
                report.failed += 1
                report.failed_telegram_ids.append(user.telegram_id)
                await self.notifications.mark_delivery(
                    notification.id, user.id, DeliveryState.FAILED, result.error
                )
        logger.info(
            "notification.pushed",
            notification_id=notification.id,
            type=type.value,
            sent=report.sent,
            failed=report.failed,
        )
        return report

    async def notify_user(
        self,
        user: User,
        *,
        type: NotificationType,
        title: str,
        body: str,
        message_text: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        order_id: int | None = None,
    ) -> PushReport:
        """Send a transactional notification (order/payment updates)."""
        return await self.push(
            type=type,
            title=title,
            body=body,
            recipients=[user],
            message_text=message_text,
            reply_markup=reply_markup,
            order_id=order_id,
        )

    # --------------------------------------------------------- stock alerts
    async def subscribe_stock_alert(self, plan: Plan, user: User) -> StockAlert:
        """Register a "🔔 Notify Me" request for a sold-out plan."""
        if plan.is_purchasable:
            raise ValidationError("This plan is available right now — no need to wait.")
        alert = await self.alerts.get_for_user(plan.id, user.id)
        if alert is None:
            alert = await self.alerts.create(
                plan_id=plan.id,
                user_id=user.id,
                telegram_id=user.telegram_id,
                status=StockAlertStatus.WAITING,
            )
        else:
            alert.status = StockAlertStatus.WAITING
            alert.notified_at = None
            await self.session.flush()
        return alert

    async def unsubscribe_stock_alert(self, plan_id: int, user: User) -> bool:
        alert = await self.alerts.get_for_user(plan_id, user.id)
        if alert is None or alert.status is not StockAlertStatus.WAITING:
            return False
        alert.status = StockAlertStatus.CANCELLED
        await self.session.flush()
        return True

    async def is_subscribed(self, plan_id: int, user: User) -> bool:
        alert = await self.alerts.get_for_user(plan_id, user.id)
        return alert is not None and alert.status is StockAlertStatus.WAITING

    async def waiting_users(self, plan_id: int) -> Sequence[User]:
        return await self.alerts.waiting_users(plan_id)

    async def waiting_count(self, plan_id: int) -> int:
        return await self.alerts.count_waiting(plan_id)

    async def my_alerts(self, user: User, page: int, per_page: int) -> Page[StockAlert]:
        return await self.alerts.paginate_for_user(user.id, page, per_page)

    async def notify_back_in_stock(
        self,
        plan: Plan,
        *,
        title: str,
        body: str,
        message_text: str,
        recipients: Sequence[User],
        reply_markup: InlineKeyboardMarkup | None = None,
        admin: Admin | None = None,
        interested_only: bool = True,
    ) -> PushReport:
        """Announce restocked availability and close the waiting list."""
        report = await self.push(
            type=NotificationType.STOCK_AVAILABLE,
            title=title,
            body=body,
            recipients=recipients,
            message_text=message_text,
            reply_markup=reply_markup,
            plan_id=plan.id,
            product_id=plan.product_id,
            created_by_telegram_id=admin.telegram_id if admin else None,
            is_broadcast=not interested_only,
        )
        if interested_only:
            await self.alerts.mark_notified(plan.id, [user.id for user in recipients])
        if admin is not None:
            await self.logs.log(
                admin.telegram_id,
                AdminAction.ADMIN_SENT_STOCK_NOTIFICATION,
                admin_username=admin.username,
                target_type="plan",
                target_id=plan.id,
                description=(
                    f"{plan.name}: notified {report.sent}/{report.total} "
                    f"({'waiting list' if interested_only else 'all users'})"
                ),
            )
        return report

    # -------------------------------------------------------------- audiences
    async def notifiable_users(self) -> Sequence[User]:
        return await self.users.notifiable()
