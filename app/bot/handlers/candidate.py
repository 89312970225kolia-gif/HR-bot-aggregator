from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.types import Message

from app.config import Settings
from app.db.models import ApplicationStage
from app.db.repository import Repository
from app.services.application_flow import ApplicationFlowService

ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


def build_candidate_router(
    repository: Repository, flow: ApplicationFlowService, settings: Settings
) -> Router:
    router = Router(name="candidate")

    @router.message(F.document)
    async def receive_resume(message: Message) -> None:
        if message.from_user is None or message.document is None:
            return
        application = await repository.get_latest_application(message.from_user.id)
        if application is None:
            await message.answer("Сначала отправьте команду /start.")
            return
        if application.stage != ApplicationStage.WAITING_RESUME:
            await message.answer(_message_for_stage(application.stage))
            return

        document = message.document
        filename = document.file_name or ""
        suffix = Path(filename).suffix.lower()
        mime_type = (document.mime_type or "").lower()
        if suffix not in ALLOWED_MIME_TYPES or mime_type not in ALLOWED_MIME_TYPES[suffix]:
            await message.answer("Пожалуйста, отправьте резюме в формате PDF или DOCX.")
            return
        if document.file_size is not None and document.file_size > settings.max_resume_bytes:
            await message.answer(
                f"Файл слишком большой. Максимальный размер — {settings.max_resume_mb} МБ."
            )
            return

        changed = await repository.claim_resume(
            application.application_id,
            file_id=document.file_id,
            file_unique_id=document.file_unique_id,
            filename=filename,
            mime_type=document.mime_type,
        )
        if not changed:
            current = await repository.get_application(application.application_id)
            await message.answer(
                _message_for_stage(current.stage if current else application.stage)
            )
            return
        await message.answer(
            "Резюме получил ✅\n\n"
            "Теперь отправьте, пожалуйста, сопроводительное письмо одним сообщением."
        )

    @router.message(F.text)
    async def receive_cover_letter(message: Message) -> None:
        if message.from_user is None or not message.text or message.text.startswith("/"):
            return
        application = await repository.get_latest_application(message.from_user.id)
        if application is None:
            await message.answer("Сначала отправьте команду /start.")
            return
        if application.stage != ApplicationStage.WAITING_COVER_LETTER:
            await message.answer(_message_for_stage(application.stage))
            return
        cover_letter = message.text.strip()
        if not cover_letter:
            await message.answer("Сопроводительное письмо не должно быть пустым.")
            return
        changed = await repository.claim_cover_letter(
            application.application_id, cover_letter
        )
        if not changed:
            current = await repository.get_application(application.application_id)
            await message.answer(
                _message_for_stage(current.stage if current else application.stage)
            )
            return
        await message.answer(
            "Спасибо! Резюме и сопроводительное письмо получены.\n\n"
            "Обрабатываю материалы и передаю заявку HR."
        )
        await flow.analyze(message.bot, application.application_id)

    return router


def _message_for_stage(stage: ApplicationStage) -> str:
    if stage == ApplicationStage.WAITING_RESUME:
        return "Пожалуйста, отправьте резюме в формате PDF или DOCX."
    if stage == ApplicationStage.WAITING_COVER_LETTER:
        return "Резюме уже получено. Отправьте сопроводительное письмо одним сообщением."
    if stage == ApplicationStage.ANALYSIS_IN_PROGRESS:
        return "Материалы уже обрабатываются. Повторно отправлять их не нужно."
    if stage == ApplicationStage.WAITING_HR_DECISION:
        return "Заявка уже передана HR и находится на рассмотрении."
    if stage == ApplicationStage.ANALYSIS_FAILED:
        return "Обработка завершилась технической ошибкой. Используйте /restart."
    return "Предыдущий процесс завершён. Для повторного отклика используйте /restart."
