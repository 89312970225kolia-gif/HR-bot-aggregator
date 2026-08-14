from __future__ import annotations

import json
import uuid
from typing import Any

import ydb

from app.db.models import ApplicationRecord, ApplicationStage, Decision
from app.db.repository import utc_now
from app.db.ydb_database import YdbDatabase

APPLICATION_FIELDS = (
    "application_id",
    "candidate_id",
    "vacancy_id",
    "stage",
    "started_at",
    "updated_at",
    "resume_file_id",
    "resume_file_unique_id",
    "resume_file_name",
    "resume_mime_type",
    "resume_received_at",
    "resume_text",
    "cover_letter",
    "ai_raw_response",
    "ai_result_json",
    "ai_analyzed_at",
    "hr_chat_id",
    "hr_message_id",
    "decision",
    "decision_at",
    "decided_by",
    "candidate_notified",
    "google_sheet_synced",
    "google_sheet_row",
)

FIELD_TYPES = {
    "stage": "Utf8",
    "updated_at": "Utf8",
    "resume_file_id": "Utf8",
    "resume_file_unique_id": "Utf8",
    "resume_file_name": "Utf8",
    "resume_mime_type": "Utf8",
    "resume_received_at": "Utf8",
    "resume_text": "Utf8",
    "cover_letter": "Utf8",
    "ai_raw_response": "Utf8",
    "ai_result_json": "Utf8",
    "ai_analyzed_at": "Utf8",
    "hr_chat_id": "Int64",
    "hr_message_id": "Int64",
    "decision": "Utf8",
    "decision_at": "Utf8",
    "decided_by": "Int64",
    "candidate_notified": "Bool",
    "google_sheet_synced": "Bool",
    "google_sheet_row": "Int64",
}


class YdbRepository:
    def __init__(self, database: YdbDatabase) -> None:
        self.database = database
        self.pool = database.pool

    async def upsert_vacancy(self, vacancy: dict[str, Any]) -> None:
        now = utc_now()
        query = """
        DECLARE $vacancy_id AS Utf8;
        DECLARE $title AS Utf8;
        DECLARE $company AS Utf8;
        DECLARE $active AS Bool;
        DECLARE $configuration AS Utf8;
        DECLARE $created_at AS Utf8;
        UPSERT INTO vacancies (
            vacancy_id, title, company, active, configuration, created_at
        ) VALUES (
            $vacancy_id, $title, $company, $active, $configuration, $created_at
        );
        """
        await self._execute(
            query,
            {
                "$vacancy_id": vacancy["vacancy_id"],
                "$title": vacancy["title"],
                "$company": vacancy.get("company", ""),
                "$active": bool(vacancy.get("active", True)),
                "$configuration": json.dumps(vacancy, ensure_ascii=False),
                "$created_at": now,
            },
        )

    async def get_or_create_candidate(
        self,
        telegram_user_id: int,
        telegram_username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> int:
        now = utc_now()
        values: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "created_at": now,
            "updated_at": now,
        }
        optional_values = {
            "telegram_username": telegram_username,
            "first_name": first_name,
            "last_name": last_name,
        }
        values.update({key: value for key, value in optional_values.items() if value is not None})
        columns = list(values)
        declarations = [
            f"DECLARE ${name} AS {'Int64' if name == 'telegram_user_id' else 'Utf8'};"
            for name in columns
        ]
        query = "\n".join(declarations) + (
            f"\nUPSERT INTO candidates ({', '.join(columns)}) "
            f"VALUES ({', '.join(f'${name}' for name in columns)});"
        )
        await self._execute(query, {f"${key}": value for key, value in values.items()})
        return telegram_user_id

    async def create_application(self, candidate_id: int, vacancy_id: str) -> ApplicationRecord:
        application_id = str(uuid.uuid4())
        now = utc_now()
        query = """
        DECLARE $application_id AS Utf8;
        DECLARE $candidate_id AS Int64;
        DECLARE $vacancy_id AS Utf8;
        DECLARE $stage AS Utf8;
        DECLARE $now AS Utf8;
        DECLARE $false AS Bool;
        INSERT INTO applications (
            application_id, candidate_id, vacancy_id, stage, started_at, updated_at,
            candidate_notified, google_sheet_synced
        ) VALUES (
            $application_id, $candidate_id, $vacancy_id, $stage, $now, $now,
            $false, $false
        );
        UPDATE candidates SET latest_application_id=$application_id, updated_at=$now
        WHERE telegram_user_id=$candidate_id;
        """
        await self._execute(
            query,
            {
                "$application_id": application_id,
                "$candidate_id": candidate_id,
                "$vacancy_id": vacancy_id,
                "$stage": ApplicationStage.WAITING_RESUME.value,
                "$now": now,
                "$false": False,
            },
        )
        application = await self.get_application(application_id)
        assert application is not None
        return application

    async def get_latest_application(self, telegram_user_id: int) -> ApplicationRecord | None:
        result_sets = await self._execute(
            """
            DECLARE $telegram_user_id AS Int64;
            SELECT latest_application_id FROM candidates
            WHERE telegram_user_id=$telegram_user_id;
            """,
            {"$telegram_user_id": telegram_user_id},
        )
        row = self._first_row(result_sets)
        if row is None or row["latest_application_id"] is None:
            return None
        return await self.get_application(str(row["latest_application_id"]))

    async def get_application(self, application_id: str) -> ApplicationRecord | None:
        result_sets = await self._execute(
            """
            DECLARE $application_id AS Utf8;
            SELECT * FROM applications WHERE application_id=$application_id;
            """,
            {"$application_id": application_id},
        )
        application_row = self._first_row(result_sets)
        if application_row is None:
            return None
        candidate_sets = await self._execute(
            """
            DECLARE $candidate_id AS Int64;
            SELECT telegram_user_id, telegram_username, first_name, last_name
            FROM candidates WHERE telegram_user_id=$candidate_id;
            """,
            {"$candidate_id": int(application_row["candidate_id"])},
        )
        candidate_row = self._first_row(candidate_sets)
        if candidate_row is None:
            return None
        return self._application_from_rows(application_row, candidate_row)

    async def claim_resume(
        self,
        application_id: str,
        *,
        file_id: str,
        file_unique_id: str,
        filename: str,
        mime_type: str | None,
    ) -> bool:
        fields: dict[str, Any] = {
            "resume_file_id": file_id,
            "resume_file_unique_id": file_unique_id,
            "resume_file_name": filename,
            "resume_received_at": utc_now(),
        }
        if mime_type is not None:
            fields["resume_mime_type"] = mime_type
        return await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_RESUME,
            ApplicationStage.WAITING_COVER_LETTER,
            fields,
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
            {"google_sheet_synced": False},
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
        changed = await self._conditional_update(
            application_id,
            ApplicationStage.WAITING_HR_DECISION,
            ApplicationStage(decision.value),
            {
                "decision": decision.value,
                "decision_at": utc_now(),
                "decided_by": decided_by,
            },
        )
        return changed, await self.get_application(application_id)

    async def mark_candidate_notified(self, application_id: str) -> None:
        await self._update_fields(application_id, {"candidate_notified": True})

    async def mark_sheet_sync(
        self, application_id: str, *, synced: bool, row: int | None = None
    ) -> None:
        fields: dict[str, Any] = {"google_sheet_synced": synced}
        if row is not None:
            fields["google_sheet_row"] = row
        await self._update_fields(application_id, fields)

    async def list_unsynced(self) -> list[ApplicationRecord]:
        result_sets = await self._execute(
            """
            SELECT application_id FROM applications
            WHERE google_sheet_synced=false AND ai_result_json IS NOT NULL;
            """
        )
        rows = result_sets[0].rows if result_sets else []
        applications = [await self.get_application(str(row["application_id"])) for row in rows]
        return [application for application in applications if application is not None]

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
        declarations = [
            "DECLARE $application_id AS Utf8;",
            "DECLARE $expected_stage AS Utf8;",
        ]
        parameters: dict[str, Any] = {
            "$application_id": application_id,
            "$expected_stage": expected_stage.value,
        }
        assignments = []
        for name, value in values.items():
            declarations.append(f"DECLARE ${name} AS {FIELD_TYPES[name]};")
            parameters[f"${name}"] = value
            assignments.append(f"{name}=${name}")
        query = "\n".join(declarations) + (
            f"\nUPDATE applications SET {', '.join(assignments)} "
            "WHERE application_id=$application_id AND stage=$expected_stage;\n"
            "SELECT COUNT(*) AS changed FROM applications "
            "WHERE application_id=$application_id AND stage=$stage "
            "AND updated_at=$updated_at;"
        )
        result_sets = await self._execute(query, parameters, idempotent=False)
        row = self._first_row(result_sets)
        return row is not None and int(row["changed"]) == 1

    async def _update_fields(self, application_id: str, fields: dict[str, Any]) -> None:
        values = dict(fields)
        values["updated_at"] = utc_now()
        declarations = ["DECLARE $application_id AS Utf8;"]
        parameters: dict[str, Any] = {"$application_id": application_id}
        assignments = []
        for name, value in values.items():
            declarations.append(f"DECLARE ${name} AS {FIELD_TYPES[name]};")
            parameters[f"${name}"] = value
            assignments.append(f"{name}=${name}")
        query = "\n".join(declarations) + (
            f"\nUPDATE applications SET {', '.join(assignments)} "
            "WHERE application_id=$application_id;"
        )
        await self._execute(query, parameters)

    async def _execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        *,
        idempotent: bool = True,
    ) -> list[Any]:
        return await self.pool.execute_with_retries(
            query,
            parameters,
            retry_settings=ydb.RetrySettings(idempotent=idempotent),
        )

    @staticmethod
    def _first_row(result_sets: list[Any]) -> Any | None:
        if not result_sets or not result_sets[-1].rows:
            return None
        return result_sets[-1].rows[0]

    @staticmethod
    def _application_from_rows(application: Any, candidate: Any) -> ApplicationRecord:
        values = {name: application[name] for name in APPLICATION_FIELDS}
        return ApplicationRecord(
            application_id=values["application_id"],
            candidate_id=values["candidate_id"],
            vacancy_id=values["vacancy_id"],
            stage=ApplicationStage(values["stage"]),
            started_at=values["started_at"],
            updated_at=values["updated_at"],
            telegram_user_id=candidate["telegram_user_id"],
            telegram_username=candidate["telegram_username"],
            first_name=candidate["first_name"],
            last_name=candidate["last_name"],
            resume_file_id=values["resume_file_id"],
            resume_file_unique_id=values["resume_file_unique_id"],
            resume_file_name=values["resume_file_name"],
            resume_mime_type=values["resume_mime_type"],
            resume_received_at=values["resume_received_at"],
            resume_text=values["resume_text"],
            cover_letter=values["cover_letter"],
            ai_raw_response=values["ai_raw_response"],
            ai_result_json=values["ai_result_json"],
            ai_analyzed_at=values["ai_analyzed_at"],
            hr_chat_id=values["hr_chat_id"],
            hr_message_id=values["hr_message_id"],
            decision=values["decision"],
            decision_at=values["decision_at"],
            decided_by=values["decided_by"],
            candidate_notified=bool(values["candidate_notified"]),
            google_sheet_synced=bool(values["google_sheet_synced"]),
            google_sheet_row=values["google_sheet_row"],
        )
