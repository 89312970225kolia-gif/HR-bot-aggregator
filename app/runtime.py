from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import Bot, Dispatcher

from app.bot.dispatcher import create_dispatcher
from app.config import Settings
from app.db.database import Database
from app.db.repository import Repository
from app.db.ydb_database import YdbDatabase
from app.db.ydb_repository import YdbRepository
from app.services.application_flow import ApplicationFlowService
from app.services.google_sheets import GoogleSheetsService
from app.services.hr_notifications import HRNotifications
from app.services.yandex_ai import AIService, MockAIService, YandexAIService
from app.vacancies.loader import load_vacancy


@dataclass(slots=True)
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher
    ai_service: AIService
    database: Any

    async def close(self) -> None:
        await self.ai_service.close()
        await self.bot.session.close()
        close = getattr(self.database, "close", None)
        if close is not None:
            await close()


async def create_runtime(settings: Settings) -> BotRuntime:
    vacancy = load_vacancy(settings.vacancy_config_path)
    if settings.storage_backend == "ydb":
        database = YdbDatabase(
            settings.ydb_endpoint,
            settings.ydb_database,
            use_metadata_credentials=settings.ydb_use_metadata_credentials,
        )
        await database.initialize()
        repository = YdbRepository(database)
    else:
        database = Database(settings.database_path)
        await database.initialize()
        repository = Repository(database)
    await repository.upsert_vacancy(vacancy)

    ai_service = MockAIService() if settings.ai_mode == "mock" else YandexAIService(settings)
    sheets = GoogleSheetsService(settings)
    hr_notifications = HRNotifications(settings)
    flow = ApplicationFlowService(repository, ai_service, sheets, hr_notifications, vacancy)
    dispatcher = create_dispatcher(repository, flow, sheets, settings)
    return BotRuntime(
        bot=Bot(settings.telegram_bot_token),
        dispatcher=dispatcher,
        ai_service=ai_service,
        database=database,
    )
