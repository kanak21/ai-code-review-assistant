from uuid import UUID

from code_review_assistant.application.ports.review_job_queue import ReviewJobQueue
from code_review_assistant.domain.models.review_run import ReviewRun


class HandleGitHubPullRequestEvent:
    _SUPPORTED_ACTIONS = {
        "opened",
        "reopened",
        "synchronize",
        "ready_for_review",
    }

    def __init__(self, queue: ReviewJobQueue) -> None:
        self._queue = queue

    async def execute(
        self,
        payload: object,
        delivery_id: str,
    ) -> UUID | None:
        if not isinstance(payload, dict):
            raise ValueError("GitHub pull-request payload must be an object")

        action = payload.get("action")
        if action not in self._SUPPORTED_ACTIONS:
            return None

        repository = payload.get("repository")
        if not isinstance(repository, dict):
            raise ValueError("GitHub event has no repository object")

        owner = repository.get("owner")
        if not isinstance(owner, dict) or owner.get("type") != "Organization":
            raise ValueError("Pull request repository must belong to an organization")

        organization_login = owner.get("login")
        full_name = repository.get("full_name")
        if (
            not isinstance(organization_login, str)
            or not organization_login.strip()
            or not isinstance(full_name, str)
        ):
            raise ValueError("GitHub repository has invalid organization details")

        parts = full_name.split("/")
        if (
            len(parts) != 2
            or not all(parts)
            or parts[0].casefold() != organization_login.strip().casefold()
        ):
            raise ValueError("GitHub repository full_name does not match its owner")

        pull_request = payload.get("pull_request")
        if not isinstance(pull_request, dict):
            raise ValueError("GitHub event has no pull_request object")

        head = pull_request.get("head")
        revision = head.get("sha") if isinstance(head, dict) else None
        number = payload.get("number")

        run = ReviewRun(
            organization_id=organization_login.strip().casefold(),
            repository_id=full_name,
            pull_request_number=number,
            revision=revision,
        )

        return await self._queue.enqueue(run, delivery_id)