from code_review_assistant.domain.models.comment_approval import CommentApproval
from code_review_assistant.domain.models.review_result import ReviewResult


def validate_comment_approval(
    approval: CommentApproval,
    result: ReviewResult,
    current_revision: str,
) -> None:
    if not isinstance(approval, CommentApproval):
        raise ValueError("approval must be a CommentApproval")

    if not isinstance(result, ReviewResult):
        raise ValueError("result must be a ReviewResult")

    if approval.review_run != result.run:
        raise ValueError("approval must belong to this review run")

    if not approval.is_current_for(current_revision):
        raise ValueError("approval is stale for the current revision")

    result_findings = set(result.findings)
    if any(finding not in result_findings for finding in approval.selected_findings):
        raise ValueError("approved findings must belong to this review result")

    if len(set(approval.selected_findings)) != len(approval.selected_findings):
        raise ValueError("approved findings must be unique")