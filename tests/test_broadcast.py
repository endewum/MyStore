"""Broadcast audiences, delivery statistics and error tolerance."""

from __future__ import annotations

from typing import Any

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import User as TelegramUser

from app.database.models import BroadcastAudience, BroadcastStatus, OrderStatus, User
from app.services.delivery import MessageDispatcher
from app.services.exceptions import ValidationError
from app.services.registry import Services


class FakeBot:
    """Minimal stand-in for ``aiogram.Bot`` that records what was sent."""

    def __init__(self, fail_for: dict[int, Exception] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.photos: list[tuple[int, str]] = []
        self.fail_for = fail_for or {}

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        if chat_id in self.fail_for:
            raise self.fail_for[chat_id]
        self.sent.append((chat_id, text))

    async def send_photo(
        self, chat_id: int, photo: str, caption: str = "", **kwargs: Any
    ) -> None:
        if chat_id in self.fail_for:
            raise self.fail_for[chat_id]
        self.photos.append((chat_id, photo))


def _forbidden() -> TelegramForbiddenError:
    return TelegramForbiddenError(
        method=SendMessage(chat_id=1, text="x"), message="bot was blocked by the user"
    )


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=SendMessage(chat_id=1, text="x"), message=text)


async def _register(services: Services, telegram_id: int, name: str) -> User:
    return await services.users.register(
        TelegramUser(id=telegram_id, is_bot=False, first_name=name)
    )


async def test_dispatcher_reports_success(services: Services) -> None:
    bot = FakeBot()
    dispatcher = MessageDispatcher(bot, messages_per_second=1000)  # type: ignore[arg-type]

    result = await dispatcher.send(111, "hello")

    assert result.ok is True
    assert bot.sent == [(111, "hello")]


async def test_dispatcher_marks_blocked_users(services: Services) -> None:
    blocked_ids: list[int] = []
    bot = FakeBot(fail_for={222: _forbidden()})
    dispatcher = MessageDispatcher(
        bot,  # type: ignore[arg-type]
        messages_per_second=1000,
        on_blocked=lambda chat_id: _record(blocked_ids, chat_id),
    )

    result = await dispatcher.send(222, "hello")

    assert result.ok is False
    assert result.blocked is True
    assert blocked_ids == [222]


async def _record(sink: list[int], chat_id: int) -> None:
    sink.append(chat_id)


async def test_dispatcher_survives_bad_requests() -> None:
    bot = FakeBot(fail_for={333: _bad_request("chat not found")})
    dispatcher = MessageDispatcher(bot, messages_per_second=1000)  # type: ignore[arg-type]

    result = await dispatcher.send(333, "hello")

    assert result.ok is False
    assert result.blocked is True


async def test_send_many_continues_after_a_failure() -> None:
    bot = FakeBot(fail_for={2: _forbidden()})
    dispatcher = MessageDispatcher(bot, messages_per_second=1000)  # type: ignore[arg-type]
    batches: list[int] = []

    async def progress(batch: list) -> None:
        batches.append(len(batch))

    results = await dispatcher.send_many(
        [1, 2, 3], "hello", progress=progress, batch_size=2
    )

    assert [item.ok for item in results] == [True, False, True]
    assert bot.sent == [(1, "hello"), (3, "hello")]
    assert sum(batches) == 3


async def test_blocked_users_are_excluded_from_audience(
    services: Services, customer: User
) -> None:
    gone = await _register(services, 4004, "Gone")
    await services.users.mark_bot_blocked(gone.telegram_id)

    audience = await services.broadcasts.audience_users(BroadcastAudience.ACTIVE_USERS)

    assert customer.id in [user.id for user in audience]
    assert gone.id not in [user.id for user in audience]


async def test_all_users_audience_includes_unreachable(
    services: Services, customer: User
) -> None:
    gone = await _register(services, 4005, "Gone")
    await services.users.mark_bot_blocked(gone.telegram_id)

    audience = await services.broadcasts.audience_users(BroadcastAudience.ALL_USERS)

    assert {customer.id, gone.id} <= {user.id for user in audience}


async def test_customers_audience_only_has_delivered_orders(
    services: Services, customer: User, plan, admin, payment_method
) -> None:
    await _register(services, 4006, "Browser")

    order = await services.orders.create_order(customer, plan)
    await services.payments.select_method(order, customer, payment_method)
    payment = await services.payments.submit_evidence(order, customer, reference="TX")
    await services.payments.confirm(payment, admin)
    await services.orders.fulfill(order, admin, "delivered content")

    audience = await services.broadcasts.audience_users(BroadcastAudience.CUSTOMERS)

    assert [user.id for user in audience] == [customer.id]
    assert order.status is OrderStatus.DELIVERED


async def test_waiting_list_audience_requires_a_plan(services: Services) -> None:
    with pytest.raises(ValidationError):
        await services.broadcasts.audience_users(BroadcastAudience.INTERESTED_USERS)


async def test_draft_broadcast_counts_recipients(
    services: Services, customer: User, admin
) -> None:
    broadcast = await services.broadcasts.create_draft(
        body="🔥 New stock available!",
        audience=BroadcastAudience.ACTIVE_USERS,
        admin=admin,
    )

    audience = await services.broadcasts.audience_users(BroadcastAudience.ACTIVE_USERS)

    assert broadcast.status is BroadcastStatus.DRAFT
    assert broadcast.total_recipients == len(audience)
    assert customer.id in {user.id for user in audience}
    assert broadcast.progress_percent == 0


async def test_empty_broadcast_is_rejected(services: Services, admin) -> None:
    with pytest.raises(ValidationError):
        await services.broadcasts.create_draft(
            body="   ", audience=BroadcastAudience.ALL_USERS, admin=admin
        )


async def test_cancelled_broadcast_cannot_be_cancelled_twice(
    services: Services, admin
) -> None:
    broadcast = await services.broadcasts.create_draft(
        body="hello", audience=BroadcastAudience.ALL_USERS, admin=admin
    )
    await services.broadcasts.cancel(broadcast)
    broadcast.status = BroadcastStatus.COMPLETED

    with pytest.raises(ValidationError):
        await services.broadcasts.cancel(broadcast)


async def test_broadcast_progress_percentage(services: Services, admin) -> None:
    broadcast = await services.broadcasts.create_draft(
        body="hello", audience=BroadcastAudience.ALL_USERS, admin=admin
    )
    broadcast.total_recipients = 200
    broadcast.sent_count = 150
    broadcast.failed_count = 10

    assert broadcast.progress_percent == 80


async def test_estimated_delivery_time(services: Services) -> None:
    assert await services.broadcasts.estimated_seconds(100, 20) == 6
    assert await services.broadcasts.estimated_seconds(0, 20) == 1
