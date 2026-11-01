import hashlib
import hmac

import pytest

from code_review_assistant.infrastructure.github_webhook_verifier import (
    GitHubWebhookVerifier,
)
from code_review_assistant.settings import Settings


def make_verifier(secret: str = "test-webhook-secret") -> GitHubWebhookVerifier:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_secret=secret,
    )
    return GitHubWebhookVerifier(settings)


def make_signature(body: bytes, secret: str = "test-webhook-secret") -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verifier_accepts_valid_signature() -> None:
    body = b'{"action":"created"}'

    make_verifier().verify(body, make_signature(body))


@pytest.mark.parametrize(
    ("body", "signature"),
    [
        (b'{"action":"changed"}', make_signature(b'{"action":"created"}')),
        (b'{"action":"created"}', make_signature(b'{"action":"created"}', "wrong-secret")),
        (b'{"action":"created"}', None),
        (b'{"action":"created"}', "sha1=not-supported"),
        (b'{"action":"created"}', "sha256=short"),
        (b'{"action":"created"}', f"sha256={'z' * 64}"),
    ],
)
def test_verifier_rejects_invalid_signature(
    body: bytes,
    signature: str | None,
) -> None:
    with pytest.raises(ValueError):
        make_verifier().verify(body, signature)


def test_verifier_requires_configured_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_password="test-password",
        github_webhook_secret=None,
    )

    with pytest.raises(RuntimeError, match="GITHUB_WEBHOOK_SECRET"):
        GitHubWebhookVerifier(settings)