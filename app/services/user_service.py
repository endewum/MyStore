"""User registration, profile and administrator management."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import User as TelegramUser
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin, AdminAction, AdminRole, User
from app.database.repositories import (
    AdminLogRepository,
    AdminRepository,
    OrderRepository,
    UserRepository,
)
from app.services.exceptions import NotFoundError, ValidationError
from app.utils.logging import get_logger
from app.utils.pagination import Page
from app.utils.time import utcnow

logger = get_logger(__name__)


class UserService:
    """Everything about who is talking to the bot and what they may do."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.admins = AdminRepository(session)
        self.orders = OrderRepository(session)
        self.logs = AdminLogRepository(session)

    async def register(self, telegram_user: TelegramUser) -> User:
        """Create or refresh the local profile of a Telegram user."""
        user = await self.users.get_by_telegram_id(telegram_user.id)
        if user is None:
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language_code=(telegram_user.language_code or "en")[:8],
                last_activity_at=utcnow(),
            )
            try:
                await self.users.add(user)
            except IntegrityError:
                # Two updates from the same brand-new user can race here.
                await self.session.rollback()
                existing = await self.users.get_by_telegram_id(telegram_user.id)
                if existing is None:  # pragma: no cover - defensive
                    raise
                return existing
            logger.info("user.registered", telegram_id=user.telegram_id)
            return user

        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        if telegram_user.language_code:
            user.language_code = telegram_user.language_code[:8]
        user.last_activity_at = utcnow()
        # Talking to us proves the chat is reachable again.
        if user.has_blocked_bot:
            user.has_blocked_bot = False
            user.is_active = True
        await self.session.flush()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.users.get_by_telegram_id(telegram_id)

    async def require_user(self, telegram_id: int) -> User:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Please send /start to open your account first.")
        return user

    async def mark_bot_blocked(self, telegram_id: int) -> None:
        await self.users.mark_bot_blocked(telegram_id, True)

    async def toggle_notifications(self, user: User) -> bool:
        user.notifications_enabled = not user.notifications_enabled
        await self.session.flush()
        return user.notifications_enabled

    async def set_blocked(
        self, target: User, blocked: bool, *, admin: Admin | None, reason: str | None
    ) -> User:
        target.is_blocked = blocked
        target.block_reason = reason if blocked else None
        await self.session.flush()
        if admin:
            await self.logs.log(
                admin.telegram_id,
                AdminAction.ADMIN_BLOCKED_USER
                if blocked
                else AdminAction.ADMIN_UNBLOCKED_USER,
                target_type="user",
                target_id=target.id,
                description=reason,
            )
        return target

    async def paginate(self, page: int, per_page: int) -> Page[User]:
        return await self.users.paginate_users(page, per_page)

    async def search(self, query: str, page: int, per_page: int) -> Page[User]:
        if not query.strip():
            raise ValidationError("Please enter a username or Telegram ID.")
        return await self.users.search(query, page, per_page)

    async def user_stats(self, user: User) -> dict[str, int]:
        return {
            "orders": await self.orders.count(user_id=user.id),
        }

    # ----------------------------------------------------------------- admins
    async def get_admin(self, telegram_id: int) -> Admin | None:
        admin = await self.admins.get_by_telegram_id(telegram_id)
        return admin if admin and admin.is_active else None

    async def is_admin(self, telegram_id: int, required: AdminRole | None = None) -> bool:
        """Authorize by Telegram ID **and** a database role, never by username."""
        admin = await self.get_admin(telegram_id)
        if admin is None:
            return False
        return admin.has_role(required) if required else True

    async def grant_admin(
        self,
        telegram_id: int,
        role: AdminRole = AdminRole.ADMIN,
        *,
        granted_by: int | None = None,
        note: str | None = None,
        username: str | None = None,
    ) -> Admin:
        """Create (or update) an administrator, bootstrapping the user row."""
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            user = await self.users.add(
                User(telegram_id=telegram_id, username=username, first_name=username)
            )
        admin = await self.admins.get_by_telegram_id(telegram_id)
        if admin is None:
            admin = Admin(
                user_id=user.id,
                telegram_id=telegram_id,
                role=role,
                note=note,
                granted_by_telegram_id=granted_by,
            )
            await self.admins.add(admin)
            logger.info("admin.granted", telegram_id=telegram_id, role=role.value)
        else:
            admin.role = role
            admin.is_active = True
            if note:
                admin.note = note
            await self.session.flush()
        return admin

    async def revoke_admin(self, telegram_id: int) -> None:
        admin = await self.admins.get_by_telegram_id(telegram_id)
        if admin is None:
            raise NotFoundError("That user is not an administrator.")
        admin.is_active = False
        await self.session.flush()

    async def list_admins(self) -> Sequence[Admin]:
        return await self.admins.list_active()

    async def admin_telegram_ids(self) -> list[int]:
        """Telegram IDs that should receive operational alerts."""
        return [admin.telegram_id for admin in await self.admins.list_active()]

    async def touch(self, user: User) -> None:
        await self.users.touch_activity(user.id, utcnow())
