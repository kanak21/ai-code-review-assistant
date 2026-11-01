from dataclasses import dataclass
from uuid import UUID

from code_review_assistant.domain.models.review_run import ReviewRun


@dataclass(frozen=True, slots=True)
class ClaimedReviewJob:
    job_id: UUID
    run: ReviewRun
    lease_token: UUID
    attempt_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, UUID):
            raise ValueError("job_id must be a UUID")
        if not isinstance(self.run, ReviewRun):
            raise ValueError("run must be a ReviewRun")
        if not isinstance(self.lease_token, UUID):
            raise ValueError("lease_token must be a UUID")
        if (
            not isinstance(self.attempt_count, int)
            or isinstance(self.attempt_count, bool)
            or self.attempt_count < 1
        ):
            raise ValueError("attempt_count must be a positive integer")