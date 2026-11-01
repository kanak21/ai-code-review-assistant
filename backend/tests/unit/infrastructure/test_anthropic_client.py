import pytest

from code_review_assistant.infrastructure.llm import anthropic_client
from code_review_assistant.settings import Settings


def test_client_factory_rejects_missing_api_key() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        anthropic_api_key=None,
    )

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        anthropic_client.create_anthropic_client(settings)


def test_client_factory_uses_explicit_timeout_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(anthropic_client, "AsyncAnthropic", fake_client)
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        anthropic_api_key="test-key",
    )

    anthropic_client.create_anthropic_client(settings)

    assert captured == {
        "api_key": "test-key",
        "timeout": 30.0,
        "max_retries": 2,
    }