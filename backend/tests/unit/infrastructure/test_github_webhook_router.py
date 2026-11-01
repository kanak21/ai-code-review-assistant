import hashlib
import hmac

from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_review_assistant.infrastructure.github_webhook_router import (
    create_github_webhook_router,
)
from code_review_assistant.infrastructure.github_webhook_verifier import (
    GitHubWebhookVerifier,
)
from code_review_assistant.settings import Settings


class FakeEventHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def execute(self, event_name: str, payload: object) -> None:
        self.calls.append((event_name, payload))


class FakePullRequestEventHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    async def execute(self, payload: object, delivery_id: str) -> None:
        self.calls.append((payload, delivery_id))


def make_client() -> tuple[TestClient, FakeEventHandler, FakePullRequestEventHandler]:
    secret = "test-webhook-secret"
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_secret=secret,
    )
    handler = FakeEventHandler()
    pull_request_handler = FakePullRequestEventHandler()
    app = FastAPI()
    app.include_router(
        create_github_webhook_router(
            GitHubWebhookVerifier(settings),
            handler,
            pull_request_handler,
        )
    )
    return TestClient(app), handler, pull_request_handler


def signature(body: bytes) -> str:
    digest = hmac.new(
        b"test-webhook-secret",
        body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def test_router_verifies_signature_then_dispatches_event() -> None:
    client, handler, pull_request_handler = make_client()
    body = b'{"action":"created"}'

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature(body),
            "X-GitHub-Event": "installation",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert handler.calls == [("installation", {"action": "created"})]
    assert pull_request_handler.calls == []


def test_router_rejects_bad_signature_without_dispatching() -> None:
    client, handler, pull_request_handler = make_client()

    response = client.post(
        "/webhooks/github",
        content=b'{"action":"created"}',
        headers={
            "X-Hub-Signature-256": f"sha256={'0' * 64}",
            "X-GitHub-Event": "installation",
        },
    )

    assert response.status_code == 401
    assert handler.calls == []
    assert pull_request_handler.calls == []


def test_router_rejects_malformed_json_after_signature_verification() -> None:
    client, handler, pull_request_handler = make_client()
    body = b"{not-json"

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature(body),
            "X-GitHub-Event": "installation",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON payload"
    assert handler.calls == []
    assert pull_request_handler.calls == []


def test_router_rejects_missing_event_header() -> None:
    client, handler, pull_request_handler = make_client()
    body = b"{}"

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-Hub-Signature-256": signature(body)},
    )

    assert response.status_code == 400
    assert handler.calls == []
    assert pull_request_handler.calls == []


def test_router_rejects_oversized_body() -> None:
    client, handler, pull_request_handler = make_client()

    response = client.post(
        "/webhooks/github",
        content=b"x" * 1_000_001,
        headers={"X-GitHub-Event": "installation"},
    )

    assert response.status_code == 413
    assert handler.calls == []
    assert pull_request_handler.calls == []


def test_router_dispatches_signed_pull_request_with_delivery_id() -> None:
    client, _, pull_request_handler = make_client()
    body = b'{"action":"opened"}'

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature(body),
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "delivery-123",
        },
    )

    assert response.status_code == 200
    assert pull_request_handler.calls == [
        ({"action": "opened"}, "delivery-123")
    ]


def test_router_rejects_pull_request_without_delivery_id() -> None:
    client, _, pull_request_handler = make_client()
    body = b'{"action":"opened"}'

    response = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-Hub-Signature-256": signature(body),
            "X-GitHub-Event": "pull_request",
        },
    )

    assert response.status_code == 400
    assert pull_request_handler.calls == []