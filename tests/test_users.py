"""User registration and admin authorization."""

from __future__ import annotations

import pytest
from aiogram.types import User as TelegramUser

from app.database.models import AdminRole, User
from app.services.registry import Services


def _telegram_user(**overrides) -> TelegramUser:
    payload = {
        "id": 2002,
        "is_bot": False,
        "first_name": "New",
        "username": "newbie",
        "language_code": "vi",
    }
    payload.update(overrides)
    return TelegramUser(**payload)


async def test_register_creates_user(services: Services) -> None:
    user = await services.users.register(_telegram_user())

    assert user.id is not None
    assert user.telegram_id == 2002
    assert user.username == "newbie"
    assert user.language_code == "vi"
    assert user.notifications_enabled is True
    assert user.can_receive_messages is True


async def test_register_is_idempotent_and_refreshes_profile(services: Services) -> None:
    first = await services.users.register(_telegram_user())
    second = await services.users.register(_telegram_user(username="renamed"))

    assert first.id == second.id
    assert second.username == "renamed"


async def test_register_clears_blocked_bot_flag(services: Services) -> None:
    user = await services.users.register(_telegram_user())
    await services.users.mark_bot_blocked(user.telegram_id)
    await services.session.refresh(user)
    assert user.has_blocked_bot is True

    refreshed = await services.users.register(_telegram_user())
    assert refreshed.has_blocked_bot is False
    assert refreshed.is_active is True


async def test_display_name_prefers_username(customer: User) -> None:
    assert customer.display_name == "@tess"
    customer.username = None
    assert customer.display_name == "Tess Customer"


async def test_is_admin_requires_database_role(services: Services) -> None:
    assert await services.users.is_admin(9001) is False

    await services.users.grant_admin(9001, AdminRole.STAFF)

    assert await services.users.is_admin(9001) is True
    assert await services.users.is_admin(9001, AdminRole.STAFF) is True
    assert await services.users.is_admin(9001, AdminRole.ADMIN) is False
    assert await services.users.is_admin(9001, AdminRole.SUPER_ADMIN) is False


async def test_role_hierarchy() -> None:
    assert AdminRole.SUPER_ADMIN.covers(AdminRole.ADMIN)
    assert AdminRole.ADMIN.covers(AdminRole.STAFF)
    assert not AdminRole.STAFF.covers(AdminRole.ADMIN)


async def test_revoke_admin_removes_access(services: Services) -> None:
    await services.users.grant_admin(9001, AdminRole.ADMIN)
    await services.users.revoke_admin(9001)

    assert await services.users.get_admin(9001) is None
    assert await services.users.is_admin(9001) is False


async def test_blocking_user_records_reason(services: Services, customer: User, admin) -> None:
    await services.users.set_blocked(customer, True, admin=admin, reason="Chargeback")

    assert customer.is_blocked is True
    assert customer.block_reason == "Chargeback"
    assert customer.can_receive_messages is False

    await services.users.set_blocked(customer, False, admin=admin, reason=None)
    assert customer.is_blocked is False
    assert customer.block_reason is None


async def test_user_search_by_username_and_id(services: Services, customer: User) -> None:
    by_name = await services.users.search("tess", 1, 10)
    by_id = await services.users.search(str(customer.telegram_id), 1, 10)

    assert [user.id for user in by_name.items] == [customer.id]
    assert [user.id for user in by_id.items] == [customer.id]


async def test_search_rejects_blank_query(services: Services) -> None:
    from app.services.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await services.users.search("   ", 1, 10)
