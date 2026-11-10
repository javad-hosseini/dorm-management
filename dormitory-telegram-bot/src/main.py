"""Application entrypoint for the Dormitory Telegram Bot."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers import common_router, ingest_cleaned_router, raw_data_router
from src.config import settings
from src.database.repository import get_db
from src.middlewares import AlbumMiddleware, AuthMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("dormitory_bot")


async def main() -> None:
    """Initialize resources and launch the bot."""
    logger.info("Starting Dormitory Telegram Bot...")
    logger.info("Ingestion Mode: %s", settings.INGESTION_MODE)
    logger.info("Whitelisted Users Count: %d", len(settings.ALLOWED_TELEGRAM_USER_IDS))

    # Ensure local persistence directories exist
    settings.ensure_directories()

    # Initialize SQLite database
    db = get_db()
    await db.init_db()

    # Initialize Bot and Dispatcher
    bot_session = None
    if settings.TELEGRAM_PROXY_URL:
        from aiogram.client.session.aiohttp import AiohttpSession

        logger.info("Configuring Telegram bot proxy: %s", settings.TELEGRAM_PROXY_URL)
        bot_session = AiohttpSession(proxy=settings.TELEGRAM_PROXY_URL)

    bot = Bot(
        token=settings.BOT_TOKEN,
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares
    # AuthMiddleware as outer middleware to drop unauthorized requests before processing
    auth_middleware = AuthMiddleware(settings=settings)
    dp.message.outer_middleware(auth_middleware)
    dp.callback_query.outer_middleware(auth_middleware)

    # AlbumMiddleware as inner middleware on message updates to aggregate media groups
    dp.message.middleware(AlbumMiddleware(latency=0.6))

    # Register Routers
    dp.include_router(common_router)
    dp.include_router(raw_data_router)
    dp.include_router(ingest_cleaned_router)

    # Start Polling
    try:
        logger.info("Bot started successfully. Waiting for updates...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        logger.info("Shutting down bot session...")
        await bot.session.close()
        logger.info("Bot shutdown completed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user or system signal.")

