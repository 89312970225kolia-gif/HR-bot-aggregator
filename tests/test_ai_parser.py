import json

import pytest

from app.services.ai_parser import (
    AIResponseParseError,
    YandexAIResponseError,
    extract_yandex_text,
    parse_ai_json,
)


def test_clean_json(ai_json) -> None:
    result = parse_ai_json(ai_json)
    assert result.candidate_name == "Иван Иванов"
    assert result.scores.average_score == 7.75


def test_markdown_fences(ai_json) -> None:
    result = parse_ai_json(f"```json\n{ai_json}\n```")
    assert result.portfolio_status == "yes"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.pop("hr_summary"),
        lambda value: value["scores"].__setitem__("ai_tools_skills", 11),
        lambda value: value["scores"].__setitem__("portfolio_quality", "7"),
    ],
)
def test_schema_rejects_missing_range_and_type(ai_payload, mutator) -> None:
    mutator(ai_payload)
    with pytest.raises(AIResponseParseError):
        parse_ai_json(json.dumps(ai_payload))


@pytest.mark.parametrize("raw", ["", "not json", "```json\n{}"])
def test_empty_or_invalid_response(raw) -> None:
    with pytest.raises(AIResponseParseError):
        parse_ai_json(raw)


def test_native_yandex_response_is_supported(ai_json) -> None:
    payload = {"result": {"alternatives": [{"message": {"text": ai_json}}]}}
    assert extract_yandex_text(payload) == ai_json


def test_openai_compatible_response_is_supported(ai_json) -> None:
    payload = {"choices": [{"message": {"content": ai_json}}]}
    assert extract_yandex_text(payload) == ai_json


def test_missing_generated_text_is_clear() -> None:
    with pytest.raises(YandexAIResponseError, match="does not contain"):
        extract_yandex_text({"result": {}})
