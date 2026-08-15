"""Application entry point.

Runs in long-polling mode by default; set ``WEBHOOK_ENABLED=true`` to serve
Telegram webhooks over aiohttp instead.
"""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, Dispatcher

from app.bot.bootstrap import (
    bootstrap_admins,
    create_bot,
    create_dispatcher,
    set_bot_commands,
)
from app.config import Settings, get_settings
from app.database.session import Database
from app.services.registry import Services
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)

#: How often expired unpaid orders are swept, in seconds.
EXPIRY_SWEEP_INTERVAL = 300


async def _expire_orders_loop(database: Database, settings: Settings) -> None:
    """Release stock held by orders whose payment window elapsed."""
    while True:
        await asyncio.sleep(EXPIRY_SWEEP_INTERVAL)
        try:
            async with database.session() as session:
                services = Services(session, settings)
                expired = await services.orders.expire_stale_orders()
            if expired:
                logger.info("orders.expired", count=len(expired))
        except asyncio.CancelledError:
            raise
        except Exception as error:  # pragma: no cover - background resilience
            logger.error("orders.expiry_failed", error=str(error))


async def run_polling(
    bot: Bot, dispatcher: Dispatcher, database: Database, settings: Settings
) -> None:
    await bot.delete_webhook(drop_pending_updates=settings.bot.skip_updates)
    await set_bot_commands(bot)
    sweeper = asyncio.create_task(_expire_orders_loop(database, settings))
    try:
        logger.info("bot.started", mode="polling", store=settings.store.name)
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


async def run_webhook(
    bot: Bot, dispatcher: Dispatcher, database: Database, settings: Settings
) -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    if not settings.webhook.base_url:
        raise RuntimeError("WEBHOOK_BASE_URL must be set when webhooks are enabled.")

    secret = settings.webhook.secret.get_secret_value() or None
    await bot.set_webhook(
        settings.webhook.url,
        secret_token=secret,
        drop_pending_updates=settings.bot.skip_updates,
        allowed_updates=["message", "callback_query"],
    )
    await set_bot_commands(bot)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dispatcher, bot=bot, secret_token=secret
    ).register(app, path=settings.webhook.path)
    setup_application(app, dispatcher, bot=bot)

    sweeper = asyncio.create_task(_expire_orders_loop(database, settings))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.webhook.host, port=settings.webhook.port)
    logger.info(
        "bot.started",
        mode="webhook",
        url=settings.webhook.url,
        port=settings.webhook.port,
    )
    try:
        await site.start()
        await asyncio.Event().wait()
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        await runner.cleanup()


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.logging)

    database = Database(settings.db)
    bot = create_bot(settings)
    dispatcher = create_dispatcher(settings, database)

    await bootstrap_admins(database, settings)
    try:
        if settings.webhook.enabled:
            await run_webhook(bot, dispatcher, database, settings)
        else:
            await run_polling(bot, dispatcher, database, settings)
    finally:
        await bot.session.close()
        await database.dispose()
        logger.info("bot.stopped")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())
