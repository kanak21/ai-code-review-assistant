from datetime import timedelta
from typing import Protocol
from uuid import UUID

from code_review_assistant.application.models.claimed_review_job import (
    ClaimedReviewJob,
)
from code_review_assistant.domain.models.review_run import ReviewRun


class ReviewJobQueue(Protocol):
    async def enqueue(
        self,
        run: ReviewRun,
        github_delivery_id: str,
    ) -> UUID:
        """Persist a review job, idempotently."""
        ...

    async def claim(
        self,
        lease_duration: timedelta,
        max_attempts: int,
    ) -> ClaimedReviewJob | None:
        """Atomically claim one available job, or return None if none are ready."""
        ...

    async def complete(self, job: ClaimedReviewJob) -> None:
        """Mark a job complete only if the caller still owns its lease."""
        ...

    async def fail(
        self,
        job: ClaimedReviewJob,
        error: str,
        retry_delay: timedelta,
        max_attempts: int,
    ) -> None:
        """Retry later or mark terminally failed, validating lease ownership."""
        ...

    async def renew(
        self,
        job: ClaimedReviewJob,
        lease_duration: timedelta,
    ) -> None:
        """Extend the lease only if this job's current lease is still valid."""
        ...