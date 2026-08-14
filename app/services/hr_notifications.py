from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import Settings
from app.db.models import ApplicationRecord
from app.schemas.ai_result import AIResult


def _list_or_dash(values: list[str]) -> str:
    return "\n".join(f"• {value}" for value in values) if values else "—"


def format_hr_card(application: ApplicationRecord, result: AIResult) -> str:
    telegram = f"@{application.telegram_username}" if application.telegram_username else "—"
    portfolio = result.portfolio_status
    if result.portfolio_links:
        portfolio += ": " + ", ".join(result.portfolio_links)
    scores = result.scores
    return f"""👤 НОВЫЙ КАНДИДАТ

ID заявки: {application.application_id}

ФИО: {result.candidate_name or '—'}
Telegram: {telegram}
Опыт: {result.experience_summary or '—'}
Опыт от 1 года: {result.experience_1_year}
Портфолио: {portfolio}

AI-инструменты:
{_list_or_dash(result.ai_tools)}

📊 ОЦЕНКИ

AI-инструменты: {scores.ai_tools_skills}/10
Портфолио: {scores.portfolio_quality}/10
Короткие видео: {scores.short_video_skills}/10
Освоение новых AI: {scores.learning_new_ai}/10
Дисциплина: {scores.content_discipline}/10
SMM: {scores.smm_understanding}/10
Работа на результат и обучение: {scores.result_and_learning}/10
AI и автоматизация: {scores.ai_content_automation_interest}/10

✅ СИЛЬНЫЕ СТОРОНЫ
{_list_or_dash(result.strengths)}

⚠️ НЕПОДТВЕРЖДЕННЫЕ ТРЕБОВАНИЯ
{_list_or_dash(result.missing_requirements)}

⛔ СТОП-ФАКТОРЫ
{_list_or_dash(result.stop_factors)}

📝 КРАТКО ДЛЯ HR
{result.hr_summary or '—'}"""


def decision_keyboard(application_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить", callback_data=f"approve:{application_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"reject:{application_id}"
                ),
            ]
        ]
    )


class HRNotifications:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_candidate_card(
        self, bot: Bot, application: ApplicationRecord, result: AIResult
    ) -> Message:
        assert self.settings.hr_chat_id is not None
        return await bot.send_message(
            self.settings.hr_chat_id,
            format_hr_card(application, result),
            reply_markup=decision_keyboard(application.application_id),
        )

    async def send_analysis_error(self, bot: Bot, application_id: str) -> None:
        assert self.settings.hr_chat_id is not None
        await bot.send_message(
            self.settings.hr_chat_id,
            f"⚠️ Ошибка анализа кандидата\nApplication ID: {application_id}",
        )
