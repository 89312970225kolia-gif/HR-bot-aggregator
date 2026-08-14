from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.database import Database
from app.db.models import ApplicationRecord, ApplicationStage, Decision


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


APPLICATION_SELECT = """
SELECT a.*, c.telegram_user_id, c.telegram_username, c.first_name, c.last_name
FROM applications a
JOIN candidates c ON c.candidate_id = a.candidate_id
"""


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def upsert_vacancy(self, vacancy: dict[str, Any]) -> None:
        now = utc_now()
        connection = await self.database.connect()
        try:
            await connection.execute(
                """
                INSERT INTO vacancies(vacancy_id, title, company, active, configuration, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(vacancy_id) DO UPDATE SET
                    title=excluded.title,
                    company=excluded.company,
                    active=excluded.active,
                    configuration=excluded.configuration
                """,
                (
                    vacancy["vacancy_id"],
                    vacancy["title"],
                    vacancy.get("company", ""),
                    int(vacancy.get("active", True)),
                    json.dumps(vacancy, ensure_ascii=False),
                    now,
                ),
            )
            await connection.commit()
        finally:
            await connection.close()

    async def get_or_create_candidate(
        self,
        telegram_user_id: int,
        telegram_username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> int:
        now = utc_now()
        connection = await self.database.connect()
        try:
            await connection.execute(
                """
                INSERT INTO candidates(
                    telegram_user_id, telegram_username, first_name, last_name,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET
                    telegram_username=excluded.telegram_username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    updated_at=excluded.updated_at
                """,
                (telegram_user_id, telegram_username, first_name, last_name, now, now),
            )
            cursor = await connection.execute(
                "SELECT candidate_id FROM candidates WHERE telegram_user_id=?",
                (telegram_user_id,),
            )
            row = await cursor.fetchone()
            await connection.commit()
            return int(row["candidate_id"])
        finally:
            await connection.close()

    async def create_application(self, candidate_id: int, vacancy_id: str) -> ApplicationRecord:
        application_id = str(uuid.uuid4())
        now = utc_now()
        connection = await self.database.connect()
        try:
            await connection.execute(
                """
                INSERT INTO applications(
                    application_id, candidate_id, vacancy_id, stage, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    candidate_id,
                    vacancy_id,
                    ApplicationStage.WAITING_RESUME.value,
                    now,
                    now,
                ),
            )
            await connection.commit()
        finally:
            await connection.close()
        application = await self.get_application(application_id)
        assert application is not None
        return application

    async def get_latest_application(self, telegram_user_id: int) -> ApplicationRecord | None:
        connection = await self.database.connect()
        try:
            cursor = await connection.execute(
                APPLICATION_SELECT
                + " WHERE c.telegram_user_id=? ORDER BY a.started_at DESC LIMIT 1",
                (telegram_user_id,),
            )
            return self._application_from_row(await cursor.fetchone())
        finally:
            await connection.close()

    async def get_application(self, application_id: str) -> ApplicationRecord | None:
        connection = await self.database.connect()
        try:
            cursor = await connection.execute(
                APPLICATION_SELECT + " WHERE a.application_id=?",
                (application_id,),
            )
            return self._application_from_row(await cursor.fetchone())
        finally:
            await connection.close()

    async def claim_resume(
        self,
        application_id: str,
        *,
        file_id: str,
        file_unique_id: str,
        filename: str,
        mime_type: str | None,
    ) -> bool:
        now = utc_now()
        return await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_RESUME,
            ApplicationStage.WAITING_COVER_LETTER,
            {
                "resume_file_id": file_id,
                "resume_file_unique_id": file_unique_id,
                "resume_file_name": filename,
                "resume_mime_type": mime_type,
                "resume_received_at": now,
            },
        )

    async def claim_cover_letter(self, application_id: str, cover_letter: str) -> bool:
        return await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_COVER_LETTER,
            ApplicationStage.ANALYSIS_IN_PROGRESS,
            {"cover_letter": cover_letter},
        )

    async def save_resume_text(self, application_id: str, resume_text: str) -> None:
        await self._update_fields(application_id, {"resume_text": resume_text})

    async def save_ai_success(
        self, application_id: str, raw_response: str, result_json: str
    ) -> bool:
        return await self._conditional_update(
            application_id,
            ApplicationStage.ANALYSIS_IN_PROGRESS,
            ApplicationStage.WAITING_HR_DECISION,
            {
                "ai_raw_response": raw_response,
                "ai_result_json": result_json,
                "ai_analyzed_at": utc_now(),
            },
        )

    async def mark_analysis_failed(self, application_id: str) -> bool:
        return await self._conditional_update(
            application_id,
            ApplicationStage.ANALYSIS_IN_PROGRESS,
            ApplicationStage.ANALYSIS_FAILED,
            {},
        )

    async def mark_hr_delivery_failed(self, application_id: str) -> bool:
        return await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_HR_DECISION,
            ApplicationStage.ANALYSIS_FAILED,
            {"google_sheet_synced": 0},
        )

    async def save_hr_message(
        self, application_id: str, hr_chat_id: int, hr_message_id: int
    ) -> None:
        await self._update_fields(
            application_id,
            {"hr_chat_id": hr_chat_id, "hr_message_id": hr_message_id},
        )

    async def decide(
        self, application_id: str, decision: Decision, decided_by: int
    ) -> tuple[bool, ApplicationRecord | None]:
        now = utc_now()
        changed = await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_HR_DECISION,
            ApplicationStage(decision.value),
            {
                "decision": decision.value,
                "decision_at": now,
                "decided_by": decided_by,
            },
        )
        return changed, await self.get_application(application_id)

    async def mark_candidate_notified(self, application_id: str) -> None:
        await self._update_fields(application_id, {"candidate_notified": 1})

    async def mark_sheet_sync(
        self, application_id: str, *, synced: bool, row: int | None = None
    ) -> None:
        fields: dict[str, Any] = {"google_sheet_synced": int(synced)}
        if row is not None:
            fields["google_sheet_row"] = row
        await self._update_fields(application_id, fields)

    async def list_unsynced(self) -> list[ApplicationRecord]:
        connection = await self.database.connect()
        try:
            cursor = await connection.execute(
                APPLICATION_SELECT
                + " WHERE a.google_sheet_synced=0 AND a.ai_result_json IS NOT NULL"
            )
            rows = await cursor.fetchall()
            return [self._application_from_row(row) for row in rows if row is not None]
        finally:
            await connection.close()

    async def _conditional_update(
        self,
        application_id: str,
        expected_stage: ApplicationStage,
        next_stage: ApplicationStage,
        fields: dict[str, Any],
    ) -> bool:
        values = dict(fields)
        values["stage"] = next_stage.value
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in values)
        connection = await self.database.connect()
        try:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                f"UPDATE applications SET {assignments} "
                "WHERE application_id=? AND stage=?",
                (*values.values(), application_id, expected_stage.value),
            )
            await connection.commit()
            return cursor.rowcount == 1
        except Exception:
            await connection.rollback()
            raise
        finally:
            await connection.close()

    async def _update_fields(self, application_id: str, fields: dict[str, Any]) -> None:
        values = dict(fields)
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{name}=?" for name in values)
        connection = await self.database.connect()
        try:
            await connection.execute(
                f"UPDATE applications SET {assignments} WHERE application_id=?",
                (*values.values(), application_id),
            )
            await connection.commit()
        finally:
            await connection.close()

    @staticmethod
    def _application_from_row(row: Any | None) -> ApplicationRecord | None:
        if row is None:
            return None
        return ApplicationRecord(
            application_id=row["application_id"],
            candidate_id=row["candidate_id"],
            vacancy_id=row["vacancy_id"],
            stage=ApplicationStage(row["stage"]),
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            telegram_user_id=row["telegram_user_id"],
            telegram_username=row["telegram_username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            resume_file_id=row["resume_file_id"],
            resume_file_unique_id=row["resume_file_unique_id"],
            resume_file_name=row["resume_file_name"],
            resume_mime_type=row["resume_mime_type"],
            resume_received_at=row["resume_received_at"],
            resume_text=row["resume_text"],
            cover_letter=row["cover_letter"],
            ai_raw_response=row["ai_raw_response"],
            ai_result_json=row["ai_result_json"],
            ai_analyzed_at=row["ai_analyzed_at"],
            hr_chat_id=row["hr_chat_id"],
            hr_message_id=row["hr_message_id"],
            decision=row["decision"],
            decision_at=row["decision_at"],
            decided_by=row["decided_by"],
            candidate_notified=bool(row["candidate_notified"]),
            google_sheet_synced=bool(row["google_sheet_synced"]),
            google_sheet_row=row["google_sheet_row"],
        )
