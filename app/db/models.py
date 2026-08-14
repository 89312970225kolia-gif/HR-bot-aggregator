from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ApplicationStage(StrEnum):
    WAITING_RESUME = "waiting_resume"
    WAITING_COVER_LETTER = "waiting_cover_letter"
    ANALYSIS_IN_PROGRESS = "analysis_in_progress"
    WAITING_HR_DECISION = "waiting_hr_decision"
    APPROVED = "approved"
    REJECTED = "rejected"
    ANALYSIS_FAILED = "analysis_failed"


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


FINAL_STAGES = {ApplicationStage.APPROVED, ApplicationStage.REJECTED}


@dataclass(slots=True)
class ApplicationRecord:
    application_id: str
    candidate_id: int
    vacancy_id: str
    stage: ApplicationStage
    started_at: str
    updated_at: str
    telegram_user_id: int
    telegram_username: str | None
    first_name: str | None
    last_name: str | None
    resume_file_id: str | None = None
    resume_file_unique_id: str | None = None
    resume_file_name: str | None = None
    resume_mime_type: str | None = None
    resume_received_at: str | None = None
    resume_text: str | None = None
    cover_letter: str | None = None
    ai_raw_response: str | None = None
    ai_result_json: str | None = None
    ai_analyzed_at: str | None = None
    hr_chat_id: int | None = None
    hr_message_id: int | None = None
    decision: str | None = None
    decision_at: str | None = None
    decided_by: int | None = None
    candidate_notified: bool = False
    google_sheet_synced: bool = False
    google_sheet_row: int | None = None
