"""Authorization filters.

Admin access requires a matching Telegram ID **and** an active role row in the
database. Usernames are never used for authorization.
"""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

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


def has_access(admin: Admin | None, role: AdminRole = AdminRole.STAFF) -> bool:
    """Plain authorization check for handlers that answer denials themselves."""
    return admin is not None and admin.has_role(role)
