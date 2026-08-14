from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from io import BytesIO

from aiogram import Bot

from app.db.models import ApplicationStage
from app.db.repository import Repository
from app.services.google_sheets import GoogleSheetsService
from app.services.hr_notifications import HRNotifications
from app.services.resume_parser import ResumeParseError, extract_resume_text
from app.services.yandex_ai import AIService

LOGGER = logging.getLogger(__name__)


class ApplicationFlowService:
    def __init__(
        self,
        repository: Repository,
        ai_service: AIService,
        sheets: GoogleSheetsService,
        hr_notifications: HRNotifications,
        vacancy: dict,
    ) -> None:
        self.repository = repository
        self.ai_service = ai_service
        self.sheets = sheets
        self.hr_notifications = hr_notifications
        self.vacancy = vacancy
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def analyze(self, bot: Bot, application_id: str) -> None:
        async with self._locks[application_id]:
            application = await self.repository.get_application(application_id)
            if application is None or application.stage != ApplicationStage.ANALYSIS_IN_PROGRESS:
                return
            LOGGER.info(
                "analysis_started application_id=%s candidate_id=%s filename=%s",
                application_id,
                application.telegram_user_id,
                application.resume_file_name,
            )
            try:
                file_bytes = await self._download_resume(bot, application.resume_file_id)
                resume_text = await extract_resume_text(
                    file_bytes,
                    application.resume_file_name or "resume",
                    application.resume_mime_type,
                )
                await self.repository.save_resume_text(application_id, resume_text)
                analysis = await self.ai_service.analyze(
                    resume_text, application.cover_letter or "", self.vacancy
                )
                result_payload = analysis.result.model_dump(mode="json")
                result_payload["scores"].pop("average_score", None)
                result_json = json.dumps(result_payload, ensure_ascii=False)
                changed = await self.repository.save_ai_success(
                    application_id, analysis.raw_response, result_json
                )
                if not changed:
                    LOGGER.warning("analysis_result_discarded application_id=%s", application_id)
                    return
                application = await self.repository.get_application(application_id)
                assert application is not None
                await self._sync_sheets(application, analysis.result)
                hr_message = await self.hr_notifications.send_candidate_card(
                    bot, application, analysis.result
                )
                await self.repository.save_hr_message(
                    application_id, hr_message.chat.id, hr_message.message_id
                )
                LOGGER.info("analysis_completed application_id=%s", application_id)
            except ResumeParseError as error:
                await self._fail_analysis(bot, application_id, str(error))
            except Exception:
                LOGGER.exception("analysis_failed application_id=%s", application_id)
                await self._fail_analysis(
                    bot,
                    application_id,
                    "Материалы получены, но при обработке возникла временная "
                    "техническая ошибка.\n\n"
                    "Повторно отправлять резюме и сопроводительное письмо не нужно.",
                )

    async def _download_resume(self, bot: Bot, file_id: str | None) -> bytes:
        if not file_id:
            raise ResumeParseError("Сохранённый Telegram file_id резюме отсутствует.")
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise ResumeParseError("Telegram не вернул путь к сохранённому резюме.")
        destination = BytesIO()
        await bot.download_file(file.file_path, destination=destination)
        return destination.getvalue()

    async def _sync_sheets(self, application, result) -> None:
        if not self.sheets.enabled:
            return
        try:
            sync = await self.sheets.upsert(application, result)
            await self.repository.mark_sheet_sync(
                application.application_id, synced=True, row=sync.row
            )
            LOGGER.info(
                "sheets_synced application_id=%s row=%s",
                application.application_id,
                sync.row,
            )
        except Exception:
            await self.repository.mark_sheet_sync(application.application_id, synced=False)
            LOGGER.exception("sheets_sync_failed application_id=%s", application.application_id)

    async def _fail_analysis(self, bot: Bot, application_id: str, candidate_message: str) -> None:
        changed = await self.repository.mark_analysis_failed(application_id)
        if not changed:
            changed = await self.repository.mark_hr_delivery_failed(application_id)
        application = await self.repository.get_application(application_id)
        if changed and application is not None:
            await bot.send_message(application.telegram_user_id, candidate_message)
            try:
                await self.hr_notifications.send_analysis_error(bot, application_id)
            except Exception:
                LOGGER.exception("hr_error_notification_failed application_id=%s", application_id)
