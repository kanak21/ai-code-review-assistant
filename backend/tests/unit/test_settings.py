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


# def test_openai_api_key_is_optional() -> None:
#     settings = Settings(
#         _env_file=None,
#         postgres_password="test-password",
#     )

#     assert settings.openai_api_key is None


def test_openai_api_key_is_stored_as_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        openai_api_key="test-openai-key",
    )

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "test-openai-key"
    assert "test-openai-key" not in repr(settings)


def test_github_app_settings_are_optional() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
    )

    assert settings.github_app_id is None
    assert settings.github_private_key_path is None


def test_github_app_settings_load_values() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_app_id=12345,
        github_private_key_path="secrets/github-app.pem",
    )

    assert settings.github_app_id == 12345
    assert str(settings.github_private_key_path) == "secrets\\github-app.pem"


def test_github_app_id_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_password="test-password",
            github_app_id=0,
        )

def test_github_webhook_secret_is_stored_as_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_secret="test-webhook-secret",
    )

    assert settings.github_webhook_secret is not None
    assert settings.github_webhook_secret.get_secret_value() == "test-webhook-secret"
    assert "test-webhook-secret" not in repr(settings)

def test_github_webhook_is_disabled_by_default() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
    )

    assert settings.github_webhook_enabled is False

def test_github_webhook_can_be_enabled() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_enabled=True,
    )

    assert settings.github_webhook_enabled is True

def test_anthropic_model_setting_loads() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        anthropic_model="test-model",
    )

    assert settings.anthropic_model == "test-model"

def test_model_provider_settings_load() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        review_provider="ollama",
        review_model="llama3.2:latest",
        embedding_provider="ollama",
        embedding_model="nomic-embed-text:latest",
        ollama_base_url="http://127.0.0.1:11434",
    )

    assert settings.review_provider == "ollama"
    assert settings.review_model == "llama3.2:latest"
    assert settings.embedding_provider == "ollama"
    assert settings.embedding_model == "nomic-embed-text:latest"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"