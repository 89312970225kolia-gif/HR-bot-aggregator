from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from aiogram.types import Update

from app.config import get_settings
from app.logging_config import configure_logging
from app.runtime import BotRuntime, create_runtime

LOGGER = logging.getLogger(__name__)
_runtime: BotRuntime | None = None
_runtime_lock: asyncio.Lock | None = None


async def _get_runtime() -> BotRuntime:
    global _runtime, _runtime_lock
    if _runtime is not None:
        return _runtime
    if _runtime_lock is None:
        _runtime_lock = asyncio.Lock()
    async with _runtime_lock:
        if _runtime is None:
            settings = get_settings()
            configure_logging(settings.log_level)
            settings.validate_runtime()
            _runtime = await create_runtime(settings)
            LOGGER.info("Webhook runtime initialized")
    return _runtime


def _header(event: dict[str, Any], name: str) -> str:
    headers = event.get("headers") or {}
    target = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == target:
            return str(value)
    return ""


def _decode_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body", event)
    if event.get("isBase64Encoded") and isinstance(body, str):
        body = base64.b64decode(body).decode("utf-8")
    if isinstance(body, str):
        body = json.loads(body)
    if not isinstance(body, dict):
        raise ValueError("Webhook body must be a JSON object")
    return body


async def handler(event: dict[str, Any] | str, context: Any) -> dict[str, Any]:
    del context
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            return {"statusCode": 400, "body": "invalid payload"}
    if not isinstance(event, dict):
        return {"statusCode": 400, "body": "invalid payload"}
    if event.get("httpMethod") == "GET":
        return {"statusCode": 200, "body": "ok"}

    settings = get_settings()
    if settings.telegram_webhook_secret:
        supplied = _header(event, "X-Telegram-Bot-Api-Secret-Token")
        if supplied != settings.telegram_webhook_secret:
            return {"statusCode": 403, "body": "forbidden"}

    try:
        update_data = _decode_body(event)
        runtime = await _get_runtime()
        update = Update.model_validate(update_data, context={"bot": runtime.bot})
        await runtime.dispatcher.feed_update(runtime.bot, update)
    except (ValueError, json.JSONDecodeError):
        LOGGER.warning("Invalid Telegram webhook payload")
        return {"statusCode": 400, "body": "invalid payload"}
    except Exception:
        LOGGER.exception("Telegram webhook processing failed")
        return {"statusCode": 500, "body": "processing failed"}
    return {"statusCode": 200, "body": "ok"}
