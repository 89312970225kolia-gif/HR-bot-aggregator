from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from aiogram import Bot

from app import cloud_handler
from app.config import Settings


def test_decode_body_accepts_yandex_http_event() -> None:
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 2,
            "date": 0,
            "chat": {"id": 3, "type": "private"},
        },
    }
    event = {"body": json.dumps(payload)}

    assert cloud_handler._decode_body(event) == payload


def test_decode_body_accepts_base64() -> None:
    payload = {"update_id": 1}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()

    assert cloud_handler._decode_body({"body": encoded, "isBase64Encoded": True}) == payload


async def test_handler_rejects_wrong_webhook_secret(monkeypatch) -> None:
    settings = Settings(
        telegram_bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        telegram_webhook_secret="expected",
        debug=True,
    )
    monkeypatch.setattr(cloud_handler, "get_settings", lambda: settings)

    response = await cloud_handler.handler(
        {"headers": {"X-Telegram-Bot-Api-Secret-Token": "wrong"}, "body": "{}"},
        None,
    )

    assert response["statusCode"] == 403


async def test_handler_feeds_valid_update(monkeypatch) -> None:
    settings = Settings(
        telegram_bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        telegram_webhook_secret="expected",
        debug=True,
    )
    monkeypatch.setattr(cloud_handler, "get_settings", lambda: settings)
    received = []

    class FakeDispatcher:
        async def feed_update(self, bot, update):
            received.append((bot, update.update_id))

    bot = Bot(settings.telegram_bot_token)

    async def fake_runtime():
        return SimpleNamespace(bot=bot, dispatcher=FakeDispatcher())

    monkeypatch.setattr(cloud_handler, "_get_runtime", fake_runtime)
    payload = {"update_id": 42}
    try:
        response = await cloud_handler.handler(
            {
                "headers": {"x-telegram-bot-api-secret-token": "expected"},
                "body": json.dumps(payload),
            },
            None,
        )
    finally:
        await bot.session.close()

    assert response["statusCode"] == 200
    assert received == [(bot, 42)]
