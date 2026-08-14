import pytest

from app.config import Settings


def test_debug_id_bootstrap_only_requires_telegram_token() -> None:
    settings = Settings(
        _env_file=None,
        debug=True,
        telegram_bot_token="123456:debug-token",
        hr_chat_id=None,
        hr_user_id=None,
        ai_mode="yandex",
        google_sheets_enabled=True,
    )
    settings.validate_runtime()


def test_production_requires_integration_credentials() -> None:
    settings = Settings(
        _env_file=None,
        debug=False,
        telegram_bot_token="123456:debug-token",
        ai_mode="yandex",
        google_sheets_enabled=True,
    )
    with pytest.raises(ValueError, match="HR_CHAT_ID.*YANDEX_API_KEY"):
        settings.validate_runtime()


def test_blank_google_service_account_path_is_missing() -> None:
    settings = Settings(
        _env_file=None,
        google_service_account_file="",
    )

    assert settings.google_service_account_file is None
