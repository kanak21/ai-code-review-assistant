from typing import Protocol
from uuid import UUID

from code_review_assistant.application.models.claimed_review_job import (
    ClaimedReviewJob,
)
from code_review_assistant.domain.models.review_result import ReviewResult


class ReviewResultWriter(Protocol):
    async def save(
        self,
        job: ClaimedReviewJob,
        result: ReviewResult,
    ) -> UUID:
        """Persist a result only while the caller owns the job lease.

        Repeated saves for the same job must be idempotent and return the
        existing review ID.
        """
        ...