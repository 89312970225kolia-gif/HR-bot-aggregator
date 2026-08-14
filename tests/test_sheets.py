
import pytest

from app.config import Settings
from app.db.models import Decision
from app.schemas.ai_result import AIResult
from app.services.google_sheets import DEFAULT_HEADERS, GoogleSheetsService


class FakeSheets(GoogleSheetsService):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.rows = [list(DEFAULT_HEADERS)]

    async def _get_values(self, range_name: str):
        if "1:1" in range_name:
            return [self.rows[0]] if self.rows else []
        return [list(row) for row in self.rows]

    async def _append_values(self, range_name: str, values):
        self.rows.extend([list(row) for row in values])
        row_number = len(self.rows)
        return {"updates": {"updatedRange": f"Лист1!A{row_number}:Y{row_number}"}}

    async def _update_values(self, range_name: str, values):
        if "A1:" in range_name:
            if self.rows:
                self.rows[0] = list(values[0])
            else:
                self.rows.append(list(values[0]))
            return
        start = range_name.split("!A", 1)[1].split(":", 1)[0]
        row_number = int(start)
        self.rows[row_number - 1] = list(values[0])


async def ready_application(repository, vacancy, ai_json):
    candidate_id = await repository.get_or_create_candidate(
        441500343, "candidate", "Иван", "Иванов"
    )
    application = await repository.create_application(candidate_id, vacancy["vacancy_id"])
    await repository.claim_resume(
        application.application_id,
        file_id="file-id",
        file_unique_id="unique-id",
        filename="resume.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    await repository.claim_cover_letter(application.application_id, "Cover")
    await repository.save_ai_success(application.application_id, ai_json, ai_json)
    return await repository.get_application(application.application_id)


@pytest.mark.asyncio
async def test_append_then_update_without_duplicate(
    repository, vacancy, ai_json, ai_payload
) -> None:
    settings = Settings(
        _env_file=None,
        google_sheets_enabled=True,
        google_spreadsheet_id="test",
        google_sheet_name="Лист1",
    )
    sheets = FakeSheets(settings)
    application = await ready_application(repository, vacancy, ai_json)
    assert application is not None
    result = AIResult.model_validate(ai_payload)
    first = await sheets.upsert(application, result)
    assert first.row == 2
    assert len(sheets.rows) == 2

    changed, application = await repository.decide(
        application.application_id, Decision.APPROVED, 999
    )
    assert changed and application is not None
    second = await sheets.upsert(application, result)
    assert second.row == 2
    assert len(sheets.rows) == 2
    status_index = sheets.rows[0].index("Статус")
    assert sheets.rows[1][status_index] == "approved"


@pytest.mark.asyncio
async def test_column_order_can_change(repository, vacancy, ai_json, ai_payload) -> None:
    settings = Settings(
        _env_file=None,
        google_sheets_enabled=True,
        google_spreadsheet_id="test",
    )
    sheets = FakeSheets(settings)
    sheets.rows[0] = list(reversed(DEFAULT_HEADERS))
    application = await ready_application(repository, vacancy, ai_json)
    assert application is not None
    await sheets.upsert(application, AIResult.model_validate(ai_payload))
    app_index = sheets.rows[0].index("Application ID")
    assert sheets.rows[1][app_index] == application.application_id
