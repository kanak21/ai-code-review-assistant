import hashlib
import hmac

from code_review_assistant.settings import Settings


class GitHubWebhookVerifier:
    def __init__(self, settings: Settings) -> None:
        if settings.github_webhook_secret is None:
            raise RuntimeError("GITHUB_WEBHOOK_SECRET must be configured")
        self._secret = settings.github_webhook_secret.get_secret_value().encode("utf-8")

    def verify(self, body: bytes, signature: str | None) -> None:
        if not isinstance(body, bytes):
            raise ValueError("webhook body must be bytes")
        if not isinstance(signature, str) or not signature.startswith("sha256="):
            raise ValueError("missing or malformed GitHub webhook signature")

        supplied_digest = signature.removeprefix("sha256=")
        if len(supplied_digest) != 64:
            raise ValueError("malformed GitHub webhook signature")

        expected_digest = hmac.new(
            self._secret,
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(supplied_digest, expected_digest):
            raise ValueError("invalid GitHub webhook signature")