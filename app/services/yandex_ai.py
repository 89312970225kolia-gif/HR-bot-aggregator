from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.schemas.ai_result import AIResult
from app.services.ai_parser import extract_yandex_text, parse_ai_json

LOGGER = logging.getLogger(__name__)


class YandexAIError(RuntimeError):
    pass


class YandexAIRequestError(YandexAIError):
    pass


@dataclass(slots=True)
class AIAnalysis:
    raw_response: str
    result: AIResult


class AIService(Protocol):
    async def analyze(
        self, resume_text: str, cover_letter: str, vacancy: dict[str, Any]
    ) -> AIAnalysis: ...

    async def close(self) -> None: ...


def build_system_prompt(vacancy: dict[str, Any]) -> str:
    vacancy_text = json.dumps(vacancy, ensure_ascii=False, indent=2)
    schema = json.dumps(AIResult.model_json_schema(), ensure_ascii=False)
    return f"""Ты выполняешь первичный профессиональный анализ кандидата для HR.

Ты НЕ принимаешь решение о найме. Используй только информацию из резюме и
сопроводительного письма. Не делай предположений о фактах, которых нет в
материалах. Не оценивай пол, возраст, национальность, этническую принадлежность,
религию, семейное положение, здоровье, инвалидность, сексуальную ориентацию,
внешность, фотографию и другие чувствительные характеристики. Имя используй
только как идентификатор. Проверяй кандидата только относительно предоставленных
требований вакансии. Отсутствующие сведения отмечай как unknown или пустой список.
Отсутствие портфолио без явного подтверждения помещай в missing_requirements, а
не в stop_factors. Верни только валидный JSON согласно schema. Не используй Markdown.

ВАКАНСИЯ И КРИТЕРИИ:
{vacancy_text}

JSON SCHEMA:
{schema}
"""


class YandexAIService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.yandex_timeout_seconds)
        self._owns_client = client is None

    async def analyze(
        self, resume_text: str, cover_letter: str, vacancy: dict[str, Any]
    ) -> AIAnalysis:
        request_body = {
            "modelUri": self.settings.yandex_model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": str(self.settings.yandex_max_tokens),
            },
            "messages": [
                {"role": "system", "text": build_system_prompt(vacancy)},
                {
                    "role": "user",
                    "text": (
                        f"РЕЗЮМЕ:\n\n{resume_text}\n\n"
                        f"СОПРОВОДИТЕЛЬНОЕ ПИСЬМО:\n\n{cover_letter}"
                    ),
                },
            ],
            "jsonObject": True,
        }
        headers = {
            "Authorization": f"Api-Key {self.settings.yandex_api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(3):
            try:
                response = await self.client.post(
                    self.settings.yandex_api_url, json=request_body, headers=headers
                )
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == 2:
                    raise YandexAIRequestError("YandexGPT network request failed") from error
                await asyncio.sleep(2**attempt)
                continue

            request_id = response.headers.get("x-request-id") or response.headers.get(
                "x-server-trace-id"
            )
            LOGGER.info(
                "YandexGPT response status=%s request_id=%s", response.status_code, request_id
            )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
            if response.status_code >= 400:
                raise YandexAIRequestError(
                    f"YandexGPT returned HTTP {response.status_code}; request_id={request_id}"
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise YandexAIRequestError("YandexGPT returned non-JSON HTTP response") from error
            try:
                generated_text = extract_yandex_text(payload)
                return AIAnalysis(
                    raw_response=json.dumps(payload, ensure_ascii=False),
                    result=parse_ai_json(generated_text),
                )
            except Exception:
                LOGGER.exception(
                    "Invalid YandexGPT response request_id=%s top_level_keys=%s",
                    request_id,
                    sorted(payload.keys()) if isinstance(payload, dict) else [],
                )
                raise
        raise AssertionError("unreachable")

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class MockAIService:
    async def analyze(
        self, resume_text: str, cover_letter: str, vacancy: dict[str, Any]
    ) -> AIAnalysis:
        del resume_text, cover_letter, vacancy
        fixture = {
            "candidate_name": "Тестовый кандидат",
            "experience_summary": "Опыт из тестового mock-ответа",
            "experience_1_year": "unknown",
            "portfolio_status": "unknown",
            "portfolio_links": [],
            "ai_tools": ["ChatGPT"],
            "scores": {
                "ai_tools_skills": 5,
                "portfolio_quality": 0,
                "short_video_skills": 4,
                "learning_new_ai": 6,
                "content_discipline": 5,
                "smm_understanding": 4,
                "result_and_learning": 6,
                "ai_content_automation_interest": 7,
            },
            "strengths": ["Интерес к AI"],
            "missing_requirements": ["Портфолио не подтверждено"],
            "stop_factors": [],
            "hr_summary": "Mock-анализ для проверки технического контура.",
        }
        raw = json.dumps(fixture, ensure_ascii=False)
        return AIAnalysis(raw_response=raw, result=parse_ai_json(raw))

    async def close(self) -> None:
        return None
