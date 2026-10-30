from dataclasses import dataclass
from datetime import datetime

from code_review_assistant.domain.models.review_finding import ReviewFinding
from code_review_assistant.domain.models.review_run import ReviewRun


@dataclass(frozen=True, slots=True)
class CommentApproval:
    review_run: ReviewRun
    approver_id: str
    approved_revision: str
    selected_findings: tuple[ReviewFinding, ...]
    approved_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.review_run, ReviewRun):
            raise ValueError("review_run must be a ReviewRun")

        for field_name, value in (
            ("approver_id", self.approver_id),
            ("approved_revision", self.approved_revision),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        if (
            not isinstance(self.selected_findings, tuple)
            or not self.selected_findings
            or not all(
                isinstance(finding, ReviewFinding)
                for finding in self.selected_findings
            )
        ):
            raise ValueError(
                "selected_findings must be a non-empty tuple of ReviewFinding objects"
            )

        if not isinstance(self.approved_at, datetime):
            raise ValueError("approved_at must be a datetime")

        if (
            self.approved_at.tzinfo is None
            or self.approved_at.utcoffset() is None
        ):
            raise ValueError("approved_at must include a timezone")

    def is_current_for(self, current_revision: str) -> bool:
        if not isinstance(current_revision, str) or not current_revision.strip():
            raise ValueError("current_revision must not be empty")

        return (
            self.approved_revision
            == self.review_run.revision
            == current_revision
        )