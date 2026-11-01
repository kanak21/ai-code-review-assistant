import json

from fastapi import APIRouter, HTTPException, Request

from code_review_assistant.application.services.handle_github_installation_event import (
    HandleGitHubInstallationEvent,
)
from code_review_assistant.application.services.handle_github_pull_request_event import (
    HandleGitHubPullRequestEvent,
)
from code_review_assistant.infrastructure.github_webhook_verifier import (
    GitHubWebhookVerifier,
)


_MAX_BODY_BYTES = 1_000_000


def create_github_webhook_router(
    verifier: GitHubWebhookVerifier,
    installation_event_handler: HandleGitHubInstallationEvent,
    pull_request_event_handler: HandleGitHubPullRequestEvent,
) -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/github")
    async def receive_github_webhook(request: Request) -> dict[str, str]:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > _MAX_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Webhook payload too large")

        try:
            verifier.verify(
                bytes(body),
                request.headers.get("x-hub-signature-256"),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature",
            ) from exc

        event_name = request.headers.get("x-github-event")
        if not event_name:
            raise HTTPException(status_code=400, detail="Missing GitHub event header")

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400,
                detail="Webhook payload must be an object",
            )

        try:
            if event_name == "installation":
                await installation_event_handler.execute(event_name, payload)
            elif event_name == "pull_request":
                delivery_id = request.headers.get("x-github-delivery")
                if not delivery_id or not delivery_id.strip():
                    raise HTTPException(
                        status_code=400,
                        detail="Missing GitHub delivery header",
                    )
                await pull_request_event_handler.execute(payload, delivery_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid GitHub webhook event",
            ) from exc

        return {"status": "accepted"}

    return router