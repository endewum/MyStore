"""Broadcast service.

A broadcast is created as a DRAFT, previewed by the admin, and only sent after
an explicit confirmation. Sending runs as a background task with its own
database session so a long campaign never holds an update handler open, and
progress is persisted so the admin can watch it live.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Sequence

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Admin,
    AdminAction,
    Broadcast,
    BroadcastAudience,
    BroadcastStatus,
    User,
)
from app.database.repositories import (
    AdminLogRepository,
    BroadcastRepository,
    StockAlertRepository,
    UserRepository,
)
from app.database.session import Database
from app.services.delivery import DeliveryResult, MessageDispatcher
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.logging import get_logger
from app.utils.pagination import Page

logger = get_logger(__name__)

ProgressCallback = Callable[[Broadcast], Awaitable[None]]


class BroadcastService:
    def __init__(
        self, session: AsyncSession, dispatcher: MessageDispatcher | None = None
    ) -> None:
        self.session = session
        self.dispatcher = dispatcher
        self.broadcasts = BroadcastRepository(session)
        self.users = UserRepository(session)
        self.alerts = StockAlertRepository(session)
        self.logs = AdminLogRepository(session)

    async def get(self, broadcast_id: int) -> Broadcast:
        broadcast = await self.broadcasts.get(broadcast_id)
        if broadcast is None:
            raise NotFoundError("This broadcast no longer exists.")
        return broadcast

    async def create_draft(
        self,
        *,
        body: str,
        audience: BroadcastAudience,
        admin: Admin,
        title: str | None = None,
        image_file_id: str | None = None,
        button_text: str | None = None,
        button_callback: str | None = None,
        plan_id: int | None = None,
    ) -> Broadcast:
        if not body.strip():
            raise ValidationError("The broadcast text cannot be empty.")
        recipients = await self.audience_users(audience, plan_id)
        return await self.broadcasts.create(
            title=title,
            body=body.strip(),
            audience=audience,
            image_file_id=image_file_id,
            button_text=button_text,
            button_callback=button_callback,
            plan_id=plan_id,
            status=BroadcastStatus.DRAFT,
            total_recipients=len(recipients),
            created_by_telegram_id=admin.telegram_id,
        )

    async def audience_users(
        self, audience: BroadcastAudience, plan_id: int | None = None
    ) -> Sequence[User]:
        """Resolve an audience into concrete, reachable users."""
        if audience is BroadcastAudience.ALL_USERS:
            return await self.users.broadcast_audience(only_active=False)
        if audience is BroadcastAudience.CUSTOMERS:
            return await self.users.customers()
        if audience is BroadcastAudience.INTERESTED_USERS:
            if not plan_id:
                raise ValidationError("Choose a plan for the waiting-list audience.")
            return await self.alerts.waiting_users(plan_id)
        return await self.users.broadcast_audience(only_active=True)

    async def estimated_seconds(self, recipients: int, per_second: int) -> int:
        return int(recipients / max(per_second, 1)) + 1

    async def paginate_history(self, page: int, per_page: int) -> Page[Broadcast]:
        return await self.broadcasts.paginate_history(page, per_page)

    async def cancel(self, broadcast: Broadcast) -> Broadcast:
        if broadcast.status in {BroadcastStatus.SENDING, BroadcastStatus.COMPLETED}:
            raise ValidationError("This broadcast can no longer be cancelled.")
        broadcast.status = BroadcastStatus.CANCELLED
        await self.session.flush()
        return broadcast

    async def log_sent(self, broadcast: Broadcast, admin: Admin) -> None:
        await self.logs.log(
            admin.telegram_id,
            AdminAction.ADMIN_SENT_BROADCAST,
            admin_username=admin.user.username if admin.user else None,
            target_type="broadcast",
            target_id=broadcast.id,
            description=(
                f"{broadcast.audience.value}: {broadcast.sent_count} sent, "
                f"{broadcast.failed_count} failed"
            ),
        )


class BroadcastRunner:
    """Executes a broadcast in the background with persisted progress."""

    def __init__(
        self,
        database: Database,
        dispatcher: MessageDispatcher,
        *,
        batch_size: int = 25,
    ) -> None:
        self.database = database
        self.dispatcher = dispatcher
        self.batch_size = batch_size

    def start(
        self,
        broadcast_id: int,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        progress: ProgressCallback | None = None,
    ) -> asyncio.Task[None]:
        """Fire the campaign off as a task so the admin's chat stays responsive."""
        return asyncio.create_task(
            self._run(broadcast_id, reply_markup=reply_markup, progress=progress)
        )

    async def _run(
        self,
        broadcast_id: int,
        *,
        reply_markup: InlineKeyboardMarkup | None,
        progress: ProgressCallback | None,
    ) -> None:
        from app.utils.time import utcnow

        async with self.database.session() as session:
            service = BroadcastService(session, self.dispatcher)
            broadcast = await service.get(broadcast_id)
            if broadcast.status not in {
                BroadcastStatus.DRAFT,
                BroadcastStatus.SCHEDULED,
            }:
                return
            recipients = list(
                await service.audience_users(broadcast.audience, broadcast.plan_id)
            )
            broadcast.status = BroadcastStatus.SENDING
            broadcast.total_recipients = len(recipients)
            broadcast.started_at = utcnow()
            broadcast.sent_count = 0
            broadcast.failed_count = 0
            failed_ids: list[int] = []
            await session.commit()

            text = broadcast.body
            chat_ids = [user.telegram_id for user in recipients]

            async def on_batch(batch: list[DeliveryResult]) -> None:
                broadcast.sent_count += sum(1 for item in batch if item.ok)
                failures = [item.chat_id for item in batch if not item.ok]
                broadcast.failed_count += len(failures)
                failed_ids.extend(failures)
                broadcast.failed_telegram_ids = (
                    ",".join(str(chat_id) for chat_id in failed_ids[:500]) or None
                )
                await session.commit()
                if progress:
                    await progress(broadcast)

            try:
                await self.dispatcher.send_many(
                    chat_ids,
                    text,
                    reply_markup=reply_markup,
                    photo_file_id=broadcast.image_file_id,
                    progress=on_batch,
                    batch_size=self.batch_size,
                )
                broadcast.status = BroadcastStatus.COMPLETED
            except Exception as error:  # pragma: no cover - defensive
                broadcast.status = BroadcastStatus.FAILED
                logger.error(
                    "broadcast.failed", broadcast_id=broadcast_id, error=str(error)
                )
            finally:
                broadcast.finished_at = utcnow()
                await session.commit()
                if progress:
                    await progress(broadcast)
            logger.info(
                "broadcast.finished",
                broadcast_id=broadcast_id,
                sent=broadcast.sent_count,
                failed=broadcast.failed_count,
            )
