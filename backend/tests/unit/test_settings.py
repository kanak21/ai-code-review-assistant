import pytest
from pydantic import ValidationError

from code_review_assistant.settings import Settings


def test_settings_load_database_values() -> None:
    settings = Settings(
        _env_file=None,
        postgres_db="review_assistant",
        postgres_user="review_assistant",
        postgres_password="test-password",
    )

    assert settings.postgres_db == "review_assistant"
    assert settings.postgres_user == "review_assistant"
    assert settings.postgres_password.get_secret_value() == "test-password"


def test_settings_reject_invalid_port() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_password="test-password",
            postgres_port=70000,
        )