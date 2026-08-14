from __future__ import annotations

import ydb

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    telegram_user_id Int64 NOT NULL,
    telegram_username Utf8,
    first_name Utf8,
    last_name Utf8,
    created_at Utf8 NOT NULL,
    updated_at Utf8 NOT NULL,
    latest_application_id Utf8,
    PRIMARY KEY (telegram_user_id)
);

CREATE TABLE IF NOT EXISTS vacancies (
    vacancy_id Utf8 NOT NULL,
    title Utf8 NOT NULL,
    company Utf8 NOT NULL,
    active Bool NOT NULL,
    configuration Utf8 NOT NULL,
    created_at Utf8 NOT NULL,
    PRIMARY KEY (vacancy_id)
);

CREATE TABLE IF NOT EXISTS applications (
    application_id Utf8 NOT NULL,
    candidate_id Int64 NOT NULL,
    vacancy_id Utf8 NOT NULL,
    stage Utf8 NOT NULL,
    started_at Utf8 NOT NULL,
    updated_at Utf8 NOT NULL,
    resume_file_id Utf8,
    resume_file_unique_id Utf8,
    resume_file_name Utf8,
    resume_mime_type Utf8,
    resume_received_at Utf8,
    resume_text Utf8,
    cover_letter Utf8,
    ai_raw_response Utf8,
    ai_result_json Utf8,
    ai_analyzed_at Utf8,
    hr_chat_id Int64,
    hr_message_id Int64,
    decision Utf8,
    decision_at Utf8,
    decided_by Int64,
    candidate_notified Bool NOT NULL,
    google_sheet_synced Bool NOT NULL,
    google_sheet_row Int64,
    PRIMARY KEY (application_id)
);
"""


class YdbDatabase:
    def __init__(
        self,
        endpoint: str,
        database: str,
        *,
        use_metadata_credentials: bool = True,
    ) -> None:
        credentials = (
            ydb.iam.MetadataUrlCredentials()
            if use_metadata_credentials
            else ydb.credentials_from_env_variables()
        )
        self.driver = ydb.aio.Driver(
            endpoint=endpoint,
            database=database,
            credentials=credentials,
            root_certificates=ydb.load_ydb_root_certificate(),
        )
        self.pool = ydb.aio.QuerySessionPool(self.driver, size=5)

    async def initialize(self) -> None:
        await self.driver.wait(timeout=10, fail_fast=True)
        await self.pool.execute_with_retries(
            SCHEMA,
            retry_settings=ydb.RetrySettings(idempotent=True),
        )

    async def close(self) -> None:
        await self.pool.stop()
        await self.driver.stop()
