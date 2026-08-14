import json

import httpx
import pytest

from app.config import Settings
from app.services.yandex_ai import YandexAIRequestError, YandexAIService


def yandex_settings() -> Settings:
    return Settings(
        _env_file=None,
        ai_mode="yandex",
        yandex_api_key="test-key",
        yandex_folder_id="test-folder",
        yandex_timeout_seconds=1,
        google_sheets_enabled=False,
    )


@pytest.mark.asyncio
async def test_retry_on_5xx_and_native_response(ai_json, vacancy, monkeypatch) -> None:
    calls = 0
    request_payload = None

    async def no_sleep(_seconds):
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls, request_payload
        calls += 1
        request_payload = json.loads(request.content)
        if calls < 3:
            return httpx.Response(500, json={"message": "temporary"})
        return httpx.Response(
            200,
            headers={"x-request-id": "request-1"},
            json={"result": {"alternatives": [{"message": {"text": ai_json}}]}},
        )

    monkeypatch.setattr("app.services.yandex_ai.asyncio.sleep", no_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = YandexAIService(yandex_settings(), client)
    analysis = await service.analyze("resume", "cover", vacancy)

    assert calls == 3
    assert analysis.result.candidate_name == "Иван Иванов"
    assert request_payload["modelUri"] == "gpt://test-folder/yandexgpt/latest"
    assert request_payload["jsonObject"] is True
    assert request_payload["completionOptions"]["maxTokens"] == "2000"
    assert request_payload["messages"][1]["text"].startswith("РЕЗЮМЕ:")
    await client.aclose()


@pytest.mark.asyncio
async def test_no_retry_on_401(vacancy, monkeypatch) -> None:
    calls = 0

    async def forbidden_sleep(_seconds):
        raise AssertionError("401 must not be retried")

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, headers={"x-request-id": "request-401"})

    monkeypatch.setattr("app.services.yandex_ai.asyncio.sleep", forbidden_sleep)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = YandexAIService(yandex_settings(), client)

    with pytest.raises(YandexAIRequestError, match="HTTP 401"):
        await service.analyze("resume", "cover", vacancy)
    assert calls == 1
    await client.aclose()
