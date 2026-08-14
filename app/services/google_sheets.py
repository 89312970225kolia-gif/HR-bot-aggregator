from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import Settings
from app.db.models import ApplicationRecord
from app.schemas.ai_result import AIResult

LOGGER = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

DEFAULT_HEADERS = [
    "Candidate ID",
    "Application ID",
    "ФИО",
    "Telegram",
    "Опыт",
    "Опыт от 1 года",
    "Портфолио",
    "AI-инструменты",
    "AI skills",
    "Portfolio quality",
    "Short video skills",
    "Learning new AI",
    "Content discipline",
    "SMM understanding",
    "Result and learning",
    "AI/automation interest",
    "Сильные стороны",
    "Неподтвержденные требования",
    "Стоп-факторы",
    "HR summary",
    "Статус",
    "Дата заявки",
    "Resume file",
    "Cover letter",
    "Decision at",
]


class GoogleSheetsError(RuntimeError):
    pass


@dataclass(slots=True)
class SheetSyncResult:
    row: int | None
    skipped: bool = False


def application_to_sheet_values(
    application: ApplicationRecord, result: AIResult
) -> dict[str, str | int | float]:
    telegram = f"@{application.telegram_username}" if application.telegram_username else ""
    portfolio = result.portfolio_status
    if result.portfolio_links:
        portfolio += " | " + ", ".join(result.portfolio_links)
    return {
        "Candidate ID": str(application.telegram_user_id),
        "Application ID": application.application_id,
        "ФИО": result.candidate_name,
        "Telegram": telegram,
        "Опыт": result.experience_summary,
        "Опыт от 1 года": result.experience_1_year,
        "Портфолио": portfolio,
        "AI-инструменты": ", ".join(result.ai_tools),
        "AI skills": result.scores.ai_tools_skills,
        "Portfolio quality": result.scores.portfolio_quality,
        "Short video skills": result.scores.short_video_skills,
        "Learning new AI": result.scores.learning_new_ai,
        "Content discipline": result.scores.content_discipline,
        "SMM understanding": result.scores.smm_understanding,
        "Result and learning": result.scores.result_and_learning,
        "AI/automation interest": result.scores.ai_content_automation_interest,
        "Сильные стороны": ", ".join(result.strengths),
        "Неподтвержденные требования": ", ".join(result.missing_requirements),
        "Стоп-факторы": ", ".join(result.stop_factors),
        "HR summary": result.hr_summary,
        "Статус": application.stage.value,
        "Дата заявки": application.started_at,
        "Resume file": application.resume_file_name or "",
        "Cover letter": application.cover_letter or "",
        "Decision at": application.decision_at or "",
    }


def column_letter(column_number: int) -> str:
    value = ""
    number = column_number
    while number:
        number, remainder = divmod(number - 1, 26)
        value = chr(65 + remainder) + value
    return value


class GoogleSheetsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._service: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.google_sheets_enabled

    def _build_service(self) -> Any:
        if self._service is not None:
            return self._service
        if self.settings.google_service_account_json_b64:
            try:
                raw = base64.b64decode(self.settings.google_service_account_json_b64, validate=True)
                account_info = json.loads(raw.decode("utf-8"))
                credentials = Credentials.from_service_account_info(account_info, scopes=SCOPES)
            except Exception as error:
                raise GoogleSheetsError("GOOGLE_SERVICE_ACCOUNT_JSON_B64 is invalid") from error
        else:
            credentials_path = self.settings.google_service_account_file
            if credentials_path is None:
                raise GoogleSheetsError("Google service account credentials are not configured")
            path = Path(credentials_path)
            if not path.exists():
                raise GoogleSheetsError(f"Google service account file not found: {path}")
            credentials = Credentials.from_service_account_file(path, scopes=SCOPES)
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service

    async def ensure_headers(self) -> list[str]:
        if not self.enabled:
            return []
        headers = await self._get_values(f"'{self.settings.google_sheet_name}'!1:1")
        if headers and headers[0]:
            return [str(value).strip() for value in headers[0]]
        await self._update_values(
            f"'{self.settings.google_sheet_name}'!A1:{column_letter(len(DEFAULT_HEADERS))}1",
            [DEFAULT_HEADERS],
        )
        return list(DEFAULT_HEADERS)

    async def upsert(self, application: ApplicationRecord, result: AIResult) -> SheetSyncResult:
        if not self.enabled:
            return SheetSyncResult(row=None, skipped=True)
        headers = await self.ensure_headers()
        header_map = {name.strip(): index for index, name in enumerate(headers)}
        values = application_to_sheet_values(application, result)

        match_header = "Application ID" if "Application ID" in header_map else "Candidate ID"
        if match_header not in header_map:
            raise GoogleSheetsError("Sheet must contain 'Application ID' or 'Candidate ID' header")
        match_value = str(values[match_header])
        all_rows = await self._get_values(f"'{self.settings.google_sheet_name}'!A:ZZ")
        existing_row_number: int | None = None
        match_index = header_map[match_header]
        for row_number, row in enumerate(all_rows[1:], start=2):
            if match_index < len(row) and str(row[match_index]) == match_value:
                existing_row_number = row_number
                break

        if existing_row_number is None:
            row = [""] * len(headers)
        else:
            source = all_rows[existing_row_number - 1]
            row = list(source) + [""] * (len(headers) - len(source))
            row = row[: len(headers)]
        for header, value in values.items():
            if header in header_map:
                row[header_map[header]] = value

        if existing_row_number is None:
            response = await self._append_values(
                f"'{self.settings.google_sheet_name}'!A:{column_letter(len(headers))}", [row]
            )
            updated_range = response.get("updates", {}).get("updatedRange", "")
            row_number = _row_from_range(updated_range)
            return SheetSyncResult(row=row_number)

        await self._update_values(
            f"'{self.settings.google_sheet_name}'!A{existing_row_number}:"
            f"{column_letter(len(headers))}{existing_row_number}",
            [row],
        )
        return SheetSyncResult(row=existing_row_number)

    async def _get_values(self, range_name: str) -> list[list[Any]]:
        def execute() -> list[list[Any]]:
            response = (
                self._build_service()
                .spreadsheets()
                .values()
                .get(spreadsheetId=self.settings.google_spreadsheet_id, range=range_name)
                .execute()
            )
            return response.get("values", [])

        try:
            return await asyncio.to_thread(execute)
        except GoogleSheetsError:
            raise
        except Exception as error:
            raise GoogleSheetsError(f"Google Sheets read failed: {error}") from error

    async def _append_values(self, range_name: str, values: list[list[Any]]) -> dict[str, Any]:
        def execute() -> dict[str, Any]:
            return (
                self._build_service()
                .spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.settings.google_spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": values},
                )
                .execute()
            )

        try:
            return await asyncio.to_thread(execute)
        except Exception as error:
            raise GoogleSheetsError(f"Google Sheets append failed: {error}") from error

    async def _update_values(self, range_name: str, values: list[list[Any]]) -> None:
        def execute() -> None:
            (
                self._build_service()
                .spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.settings.google_spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body={"values": values},
                )
                .execute()
            )

        try:
            await asyncio.to_thread(execute)
        except Exception as error:
            raise GoogleSheetsError(f"Google Sheets update failed: {error}") from error


def _row_from_range(updated_range: str) -> int | None:
    digits = ""
    for char in reversed(updated_range.split(":", 1)[0]):
        if not char.isdigit():
            break
        digits = char + digits
    return int(digits) if digits else None


def load_ai_result(application: ApplicationRecord) -> AIResult:
    if not application.ai_result_json:
        raise GoogleSheetsError("Application has no AI result")
    return AIResult.model_validate(json.loads(application.ai_result_json))
