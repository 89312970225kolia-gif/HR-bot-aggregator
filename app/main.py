from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from app.bot.dispatcher import create_dispatcher
from app.config import get_settings
from app.db.database import Database
from app.db.repository import Repository
from app.logging_config import configure_logging
from app.services.application_flow import ApplicationFlowService
from app.services.google_sheets import GoogleSheetsService
from app.services.hr_notifications import HRNotifications
from app.services.yandex_ai import MockAIService, YandexAIService
from app.vacancies.loader import load_vacancy

LOGGER = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.validate_runtime()

    vacancy = load_vacancy(settings.vacancy_config_path)
    database = Database(settings.database_path)
    await database.initialize()
    repository = Repository(database)
    await repository.upsert_vacancy(vacancy)

    ai_service = (
        MockAIService()
        if settings.ai_mode == "mock"
        else YandexAIService(settings)
    )
    sheets = GoogleSheetsService(settings)
    hr_notifications = HRNotifications(settings)
    flow = ApplicationFlowService(
        repository, ai_service, sheets, hr_notifications, vacancy
    )
    dispatcher = create_dispatcher(repository, flow, sheets, settings)
    bot = Bot(settings.telegram_bot_token)

    try:
        await bot.delete_webhook(drop_pending_updates=settings.drop_pending_updates)
        LOGGER.info("Database initialized path=%s", settings.database_path)
        LOGGER.info("Bot started")
        LOGGER.info("Telegram mode: %s", settings.telegram_mode)
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        await ai_service.close()
        await bot.session.close()
        LOGGER.info("Bot stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
