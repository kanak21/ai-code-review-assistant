import asyncio
from uuid import uuid4

import pytest

from code_review_assistant.application.services.handle_github_pull_request_event import (
    HandleGitHubPullRequestEvent,
)
from code_review_assistant.domain.models.review_run import ReviewRun


class FakeReviewJobQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[ReviewRun, str]] = []

    async def enqueue(self, run: ReviewRun, delivery_id: str):
        self.enqueued.append((run, delivery_id))
        return uuid4()


def make_payload(action: str = "opened") -> dict[str, object]:
    return {
        "action": action,
        "number": 42,
        "repository": {
            "full_name": "Acme/Service",
            "owner": {"type": "Organization", "login": "Acme"},
        },
        "pull_request": {
            "head": {"sha": "abc123"},
        },
    }


def test_supported_event_enqueues_review_run() -> None:
    queue = FakeReviewJobQueue()
    handler = HandleGitHubPullRequestEvent(queue)
    delivery_id = "delivery-123"

    result = asyncio.run(handler.execute(make_payload("synchronize"), delivery_id))

    assert result is not None
    assert queue.enqueued == [
        (
            ReviewRun(
                organization_id="acme",
                repository_id="Acme/Service",
                pull_request_number=42,
                revision="abc123",
            ),
            delivery_id,
        )
    ]


def test_unsupported_action_is_ignored() -> None:
    queue = FakeReviewJobQueue()
    handler = HandleGitHubPullRequestEvent(queue)

    result = asyncio.run(handler.execute(make_payload("closed"), "delivery-123"))

    assert result is None
    assert queue.enqueued == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"action": "opened"},
        {
            **make_payload(),
            "repository": {
                "full_name": "AnotherOrg/Service",
                "owner": {"type": "Organization", "login": "Acme"},
            },
        },
        {
            **make_payload(),
            "repository": {
                "full_name": "Acme/Service/Extra",
                "owner": {"type": "Organization", "login": "Acme"},
            },
        },
        {
            **make_payload(),
            "number": True,
        },
        {
            **make_payload(),
            "pull_request": {"head": {"sha": ""}},
        },
    ],
)
def test_malformed_supported_event_is_rejected(payload: object) -> None:
    handler = HandleGitHubPullRequestEvent(FakeReviewJobQueue())

    with pytest.raises(ValueError):
        asyncio.run(handler.execute(payload, "delivery-123"))