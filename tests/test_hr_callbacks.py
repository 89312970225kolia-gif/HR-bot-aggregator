import pytest

from app.bot.handlers.hr import is_authorized_hr, parse_callback_data
from app.config import Settings
from app.db.models import Decision


def test_callback_uses_application_id() -> None:
    app_id = "123e4567-e89b-12d3-a456-426614174000"
    assert parse_callback_data(f"approve:{app_id}") == (Decision.APPROVED, app_id)
    assert parse_callback_data(f"reject:{app_id}") == (Decision.REJECTED, app_id)


@pytest.mark.parametrize(
    "value", [None, "approve_441500343", "approve:not-a-uuid", "unknown:123"]
)
def test_invalid_callbacks_are_rejected(value) -> None:
    assert parse_callback_data(value) is None


def test_only_configured_hr_is_authorized() -> None:
    settings = Settings(_env_file=None, hr_user_id=777)
    assert is_authorized_hr(777, settings)
    assert not is_authorized_hr(778, settings)
