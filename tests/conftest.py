from __future__ import annotations

import json

import pytest

from app.db.database import Database
from app.db.repository import Repository


@pytest.fixture
def vacancy() -> dict:
    return {
        "vacancy_id": "test_vacancy",
        "title": "Test vacancy",
        "company": "Test",
        "active": True,
        "requirements": {"mandatory": [], "preferred": []},
        "ai_criteria": [],
    }


@pytest.fixture
async def repository(tmp_path, vacancy) -> Repository:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    result = Repository(database)
    await result.upsert_vacancy(vacancy)
    return result


@pytest.fixture
def ai_payload() -> dict:
    return {
        "candidate_name": "Иван Иванов",
        "experience_summary": "Создавал короткие AI-видео.",
        "experience_1_year": "yes",
        "portfolio_status": "yes",
        "portfolio_links": ["https://example.com/portfolio"],
        "ai_tools": ["ChatGPT", "Kling"],
        "scores": {
            "ai_tools_skills": 8,
            "portfolio_quality": 7,
            "short_video_skills": 8,
            "learning_new_ai": 9,
            "content_discipline": 7,
            "smm_understanding": 6,
            "result_and_learning": 8,
            "ai_content_automation_interest": 9,
        },
        "strengths": ["Быстро учится"],
        "missing_requirements": [],
        "stop_factors": [],
        "hr_summary": "Релевантный опыт подтверждён материалами.",
    }


@pytest.fixture
def ai_json(ai_payload) -> str:
    return json.dumps(ai_payload, ensure_ascii=False)
