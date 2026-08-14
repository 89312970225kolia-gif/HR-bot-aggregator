from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    telegram_username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vacancies (
    vacancy_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    configuration TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    application_id TEXT PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(candidate_id),
    vacancy_id TEXT NOT NULL REFERENCES vacancies(vacancy_id),
    stage TEXT NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resume_file_id TEXT,
    resume_file_unique_id TEXT,
    resume_file_name TEXT,
    resume_mime_type TEXT,
    resume_received_at TEXT,
    resume_text TEXT,
    cover_letter TEXT,
    ai_raw_response TEXT,
    ai_result_json TEXT,
    ai_analyzed_at TEXT,
    hr_chat_id INTEGER,
    hr_message_id INTEGER,
    decision TEXT,
    decision_at TEXT,
    decided_by INTEGER,
    candidate_notified INTEGER NOT NULL DEFAULT 0,
    google_sheet_synced INTEGER NOT NULL DEFAULT 0,
    google_sheet_row INTEGER
);

CREATE INDEX IF NOT EXISTS idx_applications_candidate
ON applications(candidate_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_applications_stage
ON applications(stage);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.executescript(SCHEMA)
            await connection.commit()

    async def connect(self) -> aiosqlite.Connection:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("PRAGMA busy_timeout=5000")
        return connection
