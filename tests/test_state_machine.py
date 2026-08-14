import pytest

from app.db.models import ApplicationStage, Decision


async def create_application(repository, vacancy):
    candidate_id = await repository.get_or_create_candidate(
        111, "candidate", "Иван", "Иванов"
    )
    return await repository.create_application(candidate_id, vacancy["vacancy_id"])


@pytest.mark.asyncio
async def test_happy_path_to_approve(repository, vacancy, ai_json) -> None:
    application = await create_application(repository, vacancy)
    assert application.stage == ApplicationStage.WAITING_RESUME
    assert await repository.claim_resume(
        application.application_id,
        file_id="file-id",
        file_unique_id="unique-id",
        filename="resume.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert await repository.claim_cover_letter(application.application_id, "Cover")
    assert await repository.save_ai_success(application.application_id, ai_json, ai_json)
    changed, decided = await repository.decide(
        application.application_id, Decision.APPROVED, 999
    )
    assert changed
    assert decided is not None and decided.stage == ApplicationStage.APPROVED


@pytest.mark.asyncio
async def test_reject_and_repeated_decisions_are_idempotent(
    repository, vacancy, ai_json
) -> None:
    application = await create_application(repository, vacancy)
    await repository.claim_resume(
        application.application_id,
        file_id="file-id",
        file_unique_id="unique-id",
        filename="resume.pdf",
        mime_type="application/pdf",
    )
    await repository.claim_cover_letter(application.application_id, "Cover")
    await repository.save_ai_success(application.application_id, ai_json, ai_json)
    changed, _ = await repository.decide(
        application.application_id, Decision.REJECTED, 999
    )
    assert changed
    repeated, current = await repository.decide(
        application.application_id, Decision.REJECTED, 999
    )
    approve_after_reject, current = await repository.decide(
        application.application_id, Decision.APPROVED, 999
    )
    assert not repeated
    assert not approve_after_reject
    assert current is not None and current.stage == ApplicationStage.REJECTED


@pytest.mark.asyncio
async def test_wrong_transition_is_rejected(repository, vacancy) -> None:
    application = await create_application(repository, vacancy)
    assert not await repository.claim_cover_letter(application.application_id, "Too early")
    changed, current = await repository.decide(
        application.application_id, Decision.APPROVED, 999
    )
    assert not changed
    assert current is not None and current.stage == ApplicationStage.WAITING_RESUME


@pytest.mark.asyncio
async def test_failed_hr_delivery_does_not_leave_waiting_state(
    repository, vacancy, ai_json
) -> None:
    application = await create_application(repository, vacancy)
    await repository.claim_resume(
        application.application_id,
        file_id="file-id",
        file_unique_id="unique-id",
        filename="resume.pdf",
        mime_type="application/pdf",
    )
    await repository.claim_cover_letter(application.application_id, "Cover")
    await repository.save_ai_success(application.application_id, ai_json, ai_json)

    assert await repository.mark_hr_delivery_failed(application.application_id)
    current = await repository.get_application(application.application_id)
    assert current is not None
    assert current.stage == ApplicationStage.ANALYSIS_FAILED
    assert not current.google_sheet_synced


@pytest.mark.asyncio
async def test_state_survives_new_repository_instance(repository, vacancy) -> None:
    application = await create_application(repository, vacancy)
    await repository.claim_resume(
        application.application_id,
        file_id="file-id",
        file_unique_id="unique-id",
        filename="resume.pdf",
        mime_type="application/pdf",
    )
    recreated = type(repository)(repository.database)
    loaded = await recreated.get_application(application.application_id)
    assert loaded is not None
    assert loaded.stage == ApplicationStage.WAITING_COVER_LETTER
