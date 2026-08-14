from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.schemas.ai_result import AIResult


class AIResponseParseError(ValueError):
    pass


class YandexAIResponseError(AIResponseParseError):
    pass


def strip_markdown_fences(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    first_newline = text.find("\n")
    if first_newline == -1 or not text.endswith("```"):
        return text
    opening = text[:first_newline].strip().lower()
    if opening not in {"```", "```json"}:
        return text
    return text[first_newline + 1 : -3].strip()


def parse_ai_json(raw: str) -> AIResult:
    if not isinstance(raw, str) or not raw.strip():
        raise AIResponseParseError("AI response is empty")
    cleaned = strip_markdown_fences(raw)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise AIResponseParseError(f"AI returned invalid JSON: {error.msg}") from error
    try:
        return AIResult.model_validate(payload)
    except ValidationError as error:
        raise AIResponseParseError(f"AI JSON does not match schema: {error}") from error


def extract_yandex_text(payload: dict[str, Any]) -> str:
    candidates = [
        (((payload.get("result") or {}).get("alternatives") or [{}])[0]),
        ((payload.get("alternatives") or [{}])[0]),
    ]
    for candidate in candidates:
        message = candidate.get("message") if isinstance(candidate, dict) else None
        text = message.get("text") if isinstance(message, dict) else None
        if isinstance(text, str) and text.strip():
            return text

    choices = payload.get("choices") or (payload.get("body") or {}).get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    raise YandexAIResponseError("YandexGPT response does not contain generated text")
