"""Authorization filters.

Admin access requires a matching Telegram ID **and** an active role row in the
database. Usernames are never used for authorization.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database.models import Admin, AdminRole
from app.utils.logging import get_logger

logger = get_logger(__name__)

DENIED = "🚫 This area is restricted to store administrators."


class IsAdmin(BaseFilter):
    """Pass when the user holds at least ``role``."""

    def __init__(self, role: AdminRole = AdminRole.STAFF) -> None:
        self.role = role

    async def __call__(self, event: TelegramObject, admin: Admin | None = None) -> bool:
        return admin is not None and admin.has_role(self.role)


class AdminOnly(BaseFilter):
    """Like :class:`IsAdmin`, but tells unauthorized users why nothing happened.

    Used on the ``/admin`` entry points so a stray command is not silently
    ignored; deeper screens rely on :class:`IsAdmin`.
    """

    def __init__(self, role: AdminRole = AdminRole.STAFF) -> None:
        self.role = role

    async def __call__(self, event: TelegramObject, admin: Admin | None = None) -> bool:
        if admin is not None and admin.has_role(self.role):
            return True
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        logger.warning("admin.access_denied", telegram_id=user_id)
        if isinstance(event, CallbackQuery):
            await event.answer(DENIED, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(DENIED)
        return False
