"""Shared test fixtures.

Tests run against an in-memory SQLite database created from the same ORM
metadata used for MySQL migrations, so no external services are required.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("BOT_TOKEN", "123456:test-token")
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECURITY_RATE_LIMIT_ENABLED", "false")

from app.bot.bootstrap import create_dispatcher
from app.config import Settings
from app.database.models import (
    AdminRole,
    Base,
    Category,
    DeliveryType,
    InventoryItem,
    InventoryStatus,
    PaymentMethod,
    Plan,
    Product,
    User,
)
from app.database.session import Database
from app.services.registry import Services
from tests.fakes import FakeSession


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


@dataclass(slots=True)
class BotHarness:
    """A live dispatcher wired to a throwaway database and a fake API session."""

    bot: Bot
    dispatcher: Dispatcher
    database: Database
    session: FakeSession
    settings: Settings

    async def reset(self) -> None:
        """Recreate the schema and forget recorded API calls."""
        async with self.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        await self.dispatcher.storage.close()
        self.dispatcher.fsm.storage = MemoryStorage()
        self.session.clear()

    async def feed(self, update) -> None:
        await self.dispatcher.feed_update(self.bot, update)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def bot_harness(tmp_path_factory) -> AsyncIterator[BotHarness]:
    """Session-scoped because handler routers can only be attached once.

    aiogram routers are module-level singletons, so a process can build exactly
    one dispatcher; integration tests share this one and reset the database
    between cases.
    """
    db_path = tmp_path_factory.mktemp("bot") / "store.db"
    harness_settings = Settings(_env_file=None)  # type: ignore[call-arg]
    harness_settings.db.url = f"sqlite+aiosqlite:///{db_path}"
    harness_settings.security.rate_limit_enabled = False

    database = Database(harness_settings.db)
    fake_session = FakeSession()
    bot = Bot(token="123456:test-token", session=fake_session)
    dispatcher = create_dispatcher(harness_settings, database)

    harness = BotHarness(bot, dispatcher, database, fake_session, harness_settings)
    await harness.reset()
    yield harness

    await bot.session.close()
    await database.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory schema per test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def services(session: AsyncSession, settings: Settings) -> Services:
    """Service container without a bot, so nothing is pushed to Telegram."""
    return Services(session, settings, bot=None)


@pytest_asyncio.fixture
async def customer(services: Services) -> User:
    from aiogram.types import User as TelegramUser

    return await services.users.register(
        TelegramUser(
            id=1001,
            is_bot=False,
            first_name="Tess",
            last_name="Customer",
            username="tess",
            language_code="en",
        )
    )


@pytest_asyncio.fixture
async def admin(services: Services):
    return await services.users.grant_admin(
        9001, AdminRole.SUPER_ADMIN, username="boss"
    )


@pytest_asyncio.fixture
async def category(session: AsyncSession) -> Category:
    category = Category(name="AI", slug="ai", emoji="🤖", sort_order=10)
    session.add(category)
    await session.flush()
    return category


@pytest_asyncio.fixture
async def product(session: AsyncSession, category: Category) -> Product:
    product = Product(
        name="ChatGPT",
        slug="chatgpt",
        emoji="🤖",
        description="AI subscriptions",
        category_id=category.id,
        is_featured=True,
        sort_order=10,
    )
    session.add(product)
    await session.flush()
    return product


@pytest_asyncio.fixture
async def plan(session: AsyncSession, product: Product) -> Plan:
    """A manually fulfilled plan with 5 units in stock."""
    plan = Plan(
        product_id=product.id,
        name="GPT TEAM",
        duration="6 Months",
        price=Decimal("15.00"),
        currency="USD",
        stock_quantity=5,
        delivery_type=DeliveryType.MANUAL,
        sort_order=10,
    )
    session.add(plan)
    await session.flush()
    plan.product = product
    return plan


@pytest_asyncio.fixture
async def sold_out_plan(session: AsyncSession, product: Product) -> Plan:
    plan = Plan(
        product_id=product.id,
        name="GPT PLUS 30D",
        duration="30 Days",
        price=Decimal("3.08"),
        currency="USD",
        stock_quantity=0,
        delivery_type=DeliveryType.ACCOUNT,
        sort_order=20,
    )
    session.add(plan)
    await session.flush()
    plan.product = product
    return plan


@pytest_asyncio.fixture
async def code_plan(session: AsyncSession, product: Product) -> Plan:
    """A code-delivered plan backed by two inventory rows."""
    plan = Plan(
        product_id=product.id,
        name="API CODEX 1D",
        price=Decimal("3.81"),
        currency="USD",
        stock_quantity=2,
        delivery_type=DeliveryType.CODE,
        sort_order=30,
    )
    session.add(plan)
    await session.flush()
    session.add_all(
        [
            InventoryItem(
                plan_id=plan.id, value=f"CODE-{index:03d}", status=InventoryStatus.AVAILABLE
            )
            for index in (1, 2)
        ]
    )
    await session.flush()
    plan.product = product
    return plan


@pytest_asyncio.fixture
async def payment_method(session: AsyncSession) -> PaymentMethod:
    method = PaymentMethod(
        code="binance",
        name="Binance",
        emoji="🟡",
        account_identifier="123456789",
        is_enabled=True,
        sort_order=10,
    )
    session.add(method)
    await session.flush()
    return method
