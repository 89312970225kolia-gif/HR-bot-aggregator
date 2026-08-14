from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    telegram_bot_token: str = ""
    telegram_mode: Literal["polling"] = "polling"
    drop_pending_updates: bool = True

    hr_chat_id: int | None = None
    hr_user_id: int | None = None
    hr_public_username: str = "gentelman_nick"

    database_path: Path = Path("data/hr_screening.db")

    ai_mode: Literal["yandex", "mock"] = "yandex"
    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_model: str = "yandexgpt"
    yandex_model_version: str = "latest"
    yandex_api_url: str = (
        "https://ai.api.cloud.yandex.net/foundationModels/v1/completion"
    )
    yandex_timeout_seconds: float = 60.0
    yandex_max_tokens: int = 2000

    google_sheets_enabled: bool = True
    google_spreadsheet_id: str = ""
    google_sheet_name: str = "Лист1"
    google_service_account_file: Path | None = None

    max_resume_mb: int = Field(default=10, ge=1, le=50)
    debug: bool = False
    log_level: str = "INFO"

    vacancy_id: str = "ai_content_maker"
    vacancy_config_path: Path = Path("app/vacancies/ai_content_maker.yaml")

    @field_validator("hr_public_username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lstrip("@")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("google_service_account_file", mode="before")
    @classmethod
    def normalize_optional_path(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def max_resume_bytes(self) -> int:
        return self.max_resume_mb * 1024 * 1024

    @property
    def yandex_model_uri(self) -> str:
        return (
            f"gpt://{self.yandex_folder_id}/{self.yandex_model}/"
            f"{self.yandex_model_version}"
        )

    def validate_runtime(self) -> None:
        missing: list[str] = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if self.debug:
            if missing:
                raise ValueError(
                    "Missing required environment variables: " + ", ".join(missing)
                )
            return
        if self.hr_chat_id is None:
            missing.append("HR_CHAT_ID")
        if self.hr_user_id is None:
            missing.append("HR_USER_ID")
        if self.ai_mode == "yandex":
            if not self.yandex_api_key:
                missing.append("YANDEX_API_KEY")
            if not self.yandex_folder_id:
                missing.append("YANDEX_FOLDER_ID")
        if self.google_sheets_enabled:
            if not self.google_spreadsheet_id:
                missing.append("GOOGLE_SPREADSHEET_ID")
            if self.google_service_account_file is None:
                missing.append("GOOGLE_SERVICE_ACCOUNT_FILE")
        if missing:
            raise ValueError("Missing required environment variables: " + ", ".join(missing))


@lru_cache
def get_settings() -> Settings:
    return Settings()
