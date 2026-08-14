from __future__ import annotations

import logging
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.config import Settings
from app.db.models import ApplicationStage, Decision
from app.db.repository import Repository
from app.services.google_sheets import GoogleSheetsService, load_ai_result

LOGGER = logging.getLogger(__name__)

APPROVE_MESSAGE = (
    "Здравствуйте!\n\n"
    "Ваше резюме и сопроводительное письмо прошли первичный этап отбора ✅\n\n"
    "HR свяжется с вами для дальнейшего собеседования.\n\n"
    "Контакт HR: @{hr_username}\n\n"
    "Пожалуйста, обратите внимание: представитель компании свяжется с вами "
    "только с указанного аккаунта. Если вам напишут от нашего имени с другого "
    "аккаунта, не передавайте личные данные и не переходите по подозрительным "
    "ссылкам.\n\n"
    "Код заявки: {application_id}"
)

REJECT_MESSAGE = """Здравствуйте!

Спасибо за интерес к вакансии и за предоставленные материалы.

По результатам первичного отбора мы не готовы продолжить процесс по данной вакансии.

Благодарим вас за уделённое время и желаем успехов в дальнейшем поиске."""


def parse_callback_data(data: str | None) -> tuple[Decision, str] | None:
    if not data or ":" not in data:
        return None
    action, application_id = data.split(":", 1)
    if action not in {"approve", "reject"}:
        return None
    try:
        uuid.UUID(application_id)
    except ValueError:
        return None
    decision = Decision.APPROVED if action == "approve" else Decision.REJECTED
    return decision, application_id


def is_authorized_hr(actor_id: int, settings: Settings) -> bool:
    return settings.hr_user_id is not None and actor_id == settings.hr_user_id


def build_hr_router(
    repository: Repository, sheets: GoogleSheetsService, settings: Settings
) -> Router:
    router = Router(name="hr")

    @router.callback_query(F.data.func(lambda value: bool(value) and ":" in value))
    async def process_decision(callback: CallbackQuery) -> None:
        parsed = parse_callback_data(callback.data)
        if parsed is None:
            return
        if not is_authorized_hr(callback.from_user.id, settings):
            await callback.answer("Недостаточно прав.", show_alert=True)
            return

        decision, application_id = parsed
        changed, application = await repository.decide(
            application_id, decision, callback.from_user.id
        )
        if application is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return
        if not changed:
            if application.stage in {
                ApplicationStage.APPROVED,
                ApplicationStage.REJECTED,
            }:
                await callback.answer("Решение по этой заявке уже принято.", show_alert=True)
            else:
                await callback.answer("Заявка пока не готова к решению.", show_alert=True)
            return

        if sheets.enabled:
            try:
                sync = await sheets.upsert(application, load_ai_result(application))
                await repository.mark_sheet_sync(
                    application_id, synced=True, row=sync.row
                )
            except Exception:
                await repository.mark_sheet_sync(application_id, synced=False)
                LOGGER.exception("decision_sheet_sync_failed application_id=%s", application_id)

        try:
            if decision == Decision.APPROVED:
                text = APPROVE_MESSAGE.format(
                    hr_username=settings.hr_public_username,
                    application_id=application_id,
                )
            else:
                text = REJECT_MESSAGE
            await callback.bot.send_message(application.telegram_user_id, text)
            await repository.mark_candidate_notified(application_id)
        except Exception:
            LOGGER.exception(
                "candidate_decision_notification_failed application_id=%s", application_id
            )
            if settings.hr_chat_id is not None:
                await callback.bot.send_message(
                    settings.hr_chat_id,
                    "⚠️ Решение сохранено, но сообщение кандидату не отправлено.\n"
                    f"Application ID: {application_id}",
                )

        if callback.message:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                LOGGER.exception("remove_keyboard_failed application_id=%s", application_id)
        answer = "Кандидат одобрен ✅" if decision == Decision.APPROVED else "Кандидат отклонён ❌"
        await callback.answer(answer)
        LOGGER.info(
            "hr_decision application_id=%s decision=%s decided_by=%s",
            application_id,
            decision.value,
            callback.from_user.id,
        )

    return router
