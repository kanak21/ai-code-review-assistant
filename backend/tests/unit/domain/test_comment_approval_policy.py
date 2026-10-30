from datetime import datetime, timezone

import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult, CheckStatus
from code_review_assistant.domain.models.comment_approval import CommentApproval
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.policies.comment_approval_policy import (
    validate_comment_approval,
)


def make_finding(rule_id: str = "CS001") -> ReviewFinding:
    return ReviewFinding(
        rule_id=rule_id,
        severity=Severity.MEDIUM,
        title="Use a cancellation token",
        rationale="Propagate cancellation through async calls.",
        file_path="src/example.cs",
        start_line=2,
        end_line=2,
        evidence="await client.GetAsync(url);",
    )


def make_result(finding: ReviewFinding | None = None) -> ReviewResult:
    run = ReviewRun(
        organization_id="org-1",
        repository_id="repo-1",
        pull_request_number=42,
        revision="abc123",
    )
    changed_file = ChangedFile(
        path="src/example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n context\n-old\n+new\n",
    )

    return ReviewResult(
        run=run,
        changed_files=(changed_file,),
        findings=(finding or make_finding(),),
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
        coverage=ReviewCoverage(changed_files=1, analyzed_files=1),
    )


def make_approval(
    result: ReviewResult,
    findings: tuple[ReviewFinding, ...] | None = None,
    approved_revision: str = "abc123",
) -> CommentApproval:
    return CommentApproval(
        review_run=result.run,
        approver_id="reviewer-1",
        approved_revision=approved_revision,
        selected_findings=findings or result.findings,
        approved_at=datetime.now(timezone.utc),
    )


def test_policy_accepts_current_approval_for_result_findings() -> None:
    result = make_result()
    approval = make_approval(result)

    validate_comment_approval(approval, result, current_revision="abc123")


def test_policy_rejects_stale_approval() -> None:
    result = make_result()
    approval = make_approval(result)

    with pytest.raises(ValueError, match="stale"):
        validate_comment_approval(approval, result, current_revision="def456")


def test_policy_rejects_finding_not_in_result() -> None:
    result = make_result()
    approval = make_approval(result, findings=(make_finding("CS002"),))

    with pytest.raises(ValueError, match="belong to this review result"):
        validate_comment_approval(approval, result, current_revision="abc123")


def test_policy_rejects_duplicate_selected_findings() -> None:
    result = make_result()
    finding = result.findings[0]
    approval = make_approval(result, findings=(finding, finding))

    with pytest.raises(ValueError, match="must be unique"):
        validate_comment_approval(approval, result, current_revision="abc123")