from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.logging_config import configure_logging
from app.runtime import create_runtime

LOGGER = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime()

    if settings.telegram_mode != "polling":
        raise ValueError("app.main supports TELEGRAM_MODE=polling only")
    runtime = await create_runtime(settings)

    try:
        await runtime.bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        LOGGER.info("Storage initialized backend=%s", settings.storage_backend)
        LOGGER.info("Bot started")
        LOGGER.info("Telegram mode: %s", settings.telegram_mode)
        await runtime.dispatcher.start_polling(
            runtime.bot,
            allowed_updates=runtime.dispatcher.resolve_used_update_types(),
        )
    finally:
        await runtime.close()
        LOGGER.info("Bot stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
