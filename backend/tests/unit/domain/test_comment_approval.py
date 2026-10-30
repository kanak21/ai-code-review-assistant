from datetime import datetime, timezone

import pytest

from code_review_assistant.domain.models.comment_approval import CommentApproval
from code_review_assistant.domain.models.review_finding import (
    ReviewFinding,
    Severity,
)
from code_review_assistant.domain.models.review_run import ReviewRun


def make_finding() -> ReviewFinding:
    return ReviewFinding(
        rule_id="CS001",
        severity=Severity.MEDIUM,
        title="Use a cancellation token",
        rationale="Propagate cancellation through async calls.",
        file_path="src/example.cs",
        start_line=2,
        end_line=2,
        evidence="await client.GetAsync(url);",
    )


def make_approval(
    approved_revision: str = "abc123",
    approved_at: datetime | None = None,
    selected_findings: tuple[ReviewFinding, ...] = (make_finding(),),
) -> CommentApproval:
    return CommentApproval(
        review_run=ReviewRun(
            organization_id="org-1",
            repository_id="repo-1",
            pull_request_number=42,
            revision="abc123",
        ),
        approver_id="reviewer-1",
        approved_revision=approved_revision,
        selected_findings=selected_findings,
        approved_at=approved_at or datetime.now(timezone.utc),
    )


def test_approval_is_current_for_matching_revision() -> None:
    approval = make_approval()

    assert approval.is_current_for("abc123")


def test_approval_is_stale_for_different_revision() -> None:
    approval = make_approval()

    assert not approval.is_current_for("def456")


def test_approval_rejects_empty_finding_selection() -> None:
    with pytest.raises(ValueError, match="selected_findings"):
        make_approval(selected_findings=())


def test_approval_rejects_timezone_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        make_approval(approved_at=datetime(2026, 10, 30, 12, 0, 0))