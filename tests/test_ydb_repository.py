from __future__ import annotations

from types import SimpleNamespace

from app.db.ydb_repository import YdbRepository


class FakePool:
    def __init__(self, result_sets=None) -> None:
        self.calls = []
        self.result_sets = result_sets or []

    async def execute_with_retries(self, query, parameters=None, retry_settings=None):
        self.calls.append((query, parameters, retry_settings))
        return self.result_sets


def repository_with_pool(pool: FakePool) -> YdbRepository:
    return YdbRepository(SimpleNamespace(pool=pool))


async def test_candidate_id_is_stable_telegram_user_id() -> None:
    pool = FakePool()
    repository = repository_with_pool(pool)

    candidate_id = await repository.get_or_create_candidate(
        441500343, "candidate", "Иван", None
    )

    assert candidate_id == 441500343
    assert pool.calls[0][1]["$telegram_user_id"] == 441500343
    assert "$last_name" not in pool.calls[0][1]


async def test_cover_letter_transition_is_conditional() -> None:
    result = SimpleNamespace(rows=[{"changed": 1}])
    pool = FakePool([result])
    repository = repository_with_pool(pool)

    changed = await repository.claim_cover_letter("app-1", "Письмо")

    assert changed is True
    query, parameters, retry_settings = pool.calls[0]
    assert "stage=$expected_stage" in query
    assert parameters["$expected_stage"] == "waiting_cover_letter"
    assert parameters["$stage"] == "analysis_in_progress"
    assert retry_settings.idempotent is False
