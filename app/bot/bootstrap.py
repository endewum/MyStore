"""Bot/dispatcher construction and startup tasks."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import build_router
from app.bot.middlewares import register_middlewares
from app.config import Settings
from app.database.models import AdminRole
from app.database.session import Database
from app.services.registry import Services
from app.utils.logging import get_logger

logger = get_logger(__name__)

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "🏠 Open the store"),
    ("store", "🏪 Browse products"),
    ("search", "🔎 Search products"),
    ("orders", "📦 My orders"),
    ("notifications", "🔔 My notifications"),
    ("account", "👤 My account"),
    ("support", "📞 Contact support"),
    ("help", "ℹ️ How it works"),
    ("cancel", "❌ Cancel the current action"),
)


def create_storage(settings: Settings) -> BaseStorage:
    """Use Redis for FSM storage when configured, else in-memory.

    Redis is only worth it for multi-instance deployments or when in-progress
    admin wizards must survive a restart.
    """
    if not settings.redis.enabled:
        return MemoryStorage()
    from aiogram.fsm.storage.redis import RedisStorage

    logger.info("fsm.storage", backend="redis")
    return RedisStorage.from_url(settings.redis.url)


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot.token.get_secret_value(),
        default=DefaultBotProperties(
            parse_mode=settings.bot.parse_mode,
            link_preview_is_disabled=True,
        ),
    )


def create_dispatcher(settings: Settings, database: Database) -> Dispatcher:
    dispatcher = Dispatcher(storage=create_storage(settings))
    register_middlewares(dispatcher, database, settings)
    dispatcher.include_router(build_router())
    return dispatcher


async def bootstrap_admins(database: Database, settings: Settings) -> None:
    """Promote the Telegram IDs from ``BOT_ADMIN_IDS`` to SUPER_ADMIN.

    This is the only way the first administrator is created; afterwards roles
    are managed from the panel.
    """
    admin_ids = settings.bot.admin_id_list
    if not admin_ids:
        logger.warning("admins.not_configured")
        return
    async with database.session() as session:
        services = Services(session, settings)
        for telegram_id in admin_ids:
            await services.users.grant_admin(
                telegram_id,
                AdminRole.SUPER_ADMIN,
                note="Bootstrapped from BOT_ADMIN_IDS",
                username=settings.bot.admin_username.lstrip("@") or None,
            )
        await services.store_settings.ensure_defaults()
    logger.info("admins.bootstrapped", count=len(admin_ids))


async def set_bot_commands(bot: Bot) -> None:
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [BotCommand(command=name, description=text) for name, text in BOT_COMMANDS]
    )
