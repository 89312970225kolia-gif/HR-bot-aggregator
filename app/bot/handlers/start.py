from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import Settings
from app.db.models import ApplicationStage
from app.db.repository import Repository

ASK_RESUME = """Здравствуйте!

Для начала отправьте, пожалуйста, ваше резюме в формате PDF или DOCX."""

STAGE_MESSAGES = {
    ApplicationStage.WAITING_RESUME: ASK_RESUME,
    ApplicationStage.WAITING_COVER_LETTER: (
        "Резюме уже получено.\n\n"
        "Теперь отправьте, пожалуйста, сопроводительное письмо одним сообщением."
    ),
    ApplicationStage.ANALYSIS_IN_PROGRESS: (
        "Материалы уже получены и сейчас обрабатываются."
    ),
    ApplicationStage.WAITING_HR_DECISION: (
        "Ваша заявка уже передана HR и находится на рассмотрении."
    ),
    ApplicationStage.APPROVED: (
        "Предыдущий процесс завершён: заявка одобрена.\n\n"
        "Для повторного отклика используйте /restart."
    ),
    ApplicationStage.REJECTED: (
        "Предыдущий процесс завершён.\n\n"
        "Для повторного отклика используйте /restart."
    ),
    ApplicationStage.ANALYSIS_FAILED: (
        "При обработке предыдущей заявки произошла техническая ошибка.\n\n"
        "Для нового отклика используйте /restart."
    ),
}


def build_start_router(repository: Repository, settings: Settings) -> Router:
    router = Router(name="start")

    async def ensure_candidate(message: Message) -> int:
        user = message.from_user
        assert user is not None
        return await repository.get_or_create_candidate(
            user.id, user.username, user.first_name, user.last_name
        )

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        if message.from_user is None:
            return
        candidate_id = await ensure_candidate(message)
        application = await repository.get_latest_application(message.from_user.id)
        if application is None:
            application = await repository.create_application(candidate_id, settings.vacancy_id)
        await message.answer(STAGE_MESSAGES[application.stage])

    @router.message(Command("restart"))
    async def restart(message: Message) -> None:
        if message.from_user is None:
            return
        candidate_id = await ensure_candidate(message)
        application = await repository.get_latest_application(message.from_user.id)
        if application is not None and application.stage not in {
            ApplicationStage.APPROVED,
            ApplicationStage.REJECTED,
            ApplicationStage.ANALYSIS_FAILED,
        }:
            await message.answer(
                "Текущая заявка ещё не завершена.\n\n" + STAGE_MESSAGES[application.stage]
            )
            return
        await repository.create_application(candidate_id, settings.vacancy_id)
        await message.answer(ASK_RESUME)

    @router.message(Command("debug_id"))
    async def debug_id(message: Message) -> None:
        if not settings.debug or message.from_user is None:
            return
        await message.answer(
            f"user_id: {message.from_user.id}\nchat_id: {message.chat.id}"
        )

    return router
