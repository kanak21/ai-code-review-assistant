from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from code_review_assistant.application.services.handle_github_installation_event import (
    HandleGitHubInstallationEvent,
)
from code_review_assistant.application.services.handle_github_pull_request_event import (
    HandleGitHubPullRequestEvent,
)
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.github_installation_writer import (
    SqlAlchemyGitHubInstallationWriter,
)
from code_review_assistant.infrastructure.database.review_job_queue import (
    SqlAlchemyReviewJobQueue,
)
from code_review_assistant.infrastructure.github_webhook_router import (
    create_github_webhook_router,
)
from code_review_assistant.infrastructure.github_webhook_verifier import (
    GitHubWebhookVerifier,
)
from code_review_assistant.settings import Settings


def create_app(settings: Settings) -> FastAPI:
    engine = None

    if settings.github_webhook_enabled:
        if settings.github_webhook_secret is None:
            raise RuntimeError(
                "GITHUB_WEBHOOK_SECRET must be configured when "
                "GITHUB_WEBHOOK_ENABLED is true"
            )

        engine = create_database_engine(settings)
        session_factory = create_session_factory(engine)
        writer = SqlAlchemyGitHubInstallationWriter(session_factory)
        event_handler = HandleGitHubInstallationEvent(writer)
        verifier = GitHubWebhookVerifier(settings)
        review_job_queue = SqlAlchemyReviewJobQueue(session_factory)
        pull_request_event_handler = HandleGitHubPullRequestEvent(review_job_queue)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Code Review Assistant",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if settings.github_webhook_enabled:
        app.include_router(
            create_github_webhook_router(
                verifier,
                event_handler,
                pull_request_event_handler,
            )
        )

    return app


app = create_app(Settings())