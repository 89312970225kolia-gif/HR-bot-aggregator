from __future__ import annotations

import asyncio
import tempfile
from io import BytesIO
from pathlib import Path

from docx import Document

from app.db.database import Database
from app.db.models import ApplicationStage, Decision
from app.db.repository import Repository
from app.services.resume_parser import extract_resume_text
from app.services.yandex_ai import MockAIService
from app.vacancies.loader import load_vacancy


async def run() -> None:
    vacancy = load_vacancy(Path("app/vacancies/ai_content_maker.yaml"))
    with tempfile.TemporaryDirectory() as directory:
        database = Database(Path(directory) / "smoke.db")
        await database.initialize()
        repository = Repository(database)
        await repository.upsert_vacancy(vacancy)
        candidate_id = await repository.get_or_create_candidate(
            100001, "mock_candidate", "Тест", "Кандидат"
        )
        application = await repository.create_application(
            candidate_id, vacancy["vacancy_id"]
        )
        assert application.stage == ApplicationStage.WAITING_RESUME
        assert await repository.claim_resume(
            application.application_id,
            file_id="mock-file-id",
            file_unique_id="mock-unique-id",
            filename="resume.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert await repository.claim_cover_letter(
            application.application_id, "Хочу развиваться в AI-контенте."
        )

        document = Document()
        document.add_paragraph("Опыт создания коротких видео и работы с ChatGPT.")
        buffer = BytesIO()
        document.save(buffer)
        resume_text = await extract_resume_text(
            buffer.getvalue(),
            "resume.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        await repository.save_resume_text(application.application_id, resume_text)
        ai = MockAIService()
        analysis = await ai.analyze(
            resume_text, "Хочу развиваться в AI-контенте.", vacancy
        )
        result_json = analysis.result.model_dump_json(exclude_computed_fields=True)
        assert await repository.save_ai_success(
            application.application_id, analysis.raw_response, result_json
        )
        changed, decided = await repository.decide(
            application.application_id, Decision.APPROVED, 200002
        )
        assert changed and decided is not None
        assert decided.stage == ApplicationStage.APPROVED
        print(
            "Mock smoke passed: waiting_resume -> waiting_cover_letter -> "
            "analysis_in_progress -> waiting_hr_decision -> approved"
        )


if __name__ == "__main__":
    asyncio.run(run())
