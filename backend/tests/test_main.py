import pytest
from fastapi.testclient import TestClient

from code_review_assistant.main import app, create_app
from code_review_assistant.settings import Settings


def test_webhook_route_is_not_mounted_when_disabled() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_enabled=False,
    )
    test_app = create_app(settings)

    with TestClient(test_app) as client:
        response = client.post(
            "/webhooks/github",
            content=b"{}",
            headers={"X-GitHub-Event": "installation"},
        )

    assert response.status_code == 404


def test_enabling_webhook_requires_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_enabled=True,
        github_webhook_secret=None,
    )

    with pytest.raises(RuntimeError, match="GITHUB_WEBHOOK_SECRET"):
        create_app(settings)


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_route_is_mounted_when_enabled() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_enabled=True,
        github_webhook_secret="test-webhook-secret",
    )

    test_app = create_app(settings)

    with TestClient(test_app) as client:
        response = client.post(
            "/webhooks/github",
            content=b"{}",
            headers={"X-GitHub-Event": "installation"},
        )

    assert response.status_code == 401
