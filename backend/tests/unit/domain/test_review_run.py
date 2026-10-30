import pytest

from code_review_assistant.domain.models.review_run import ReviewRun


def test_review_run_is_current_for_the_same_revision() -> None:
    run = ReviewRun("org-1", "repo-1", 42, "abc123")

    assert not run.is_stale_for("abc123")


def test_review_run_is_stale_for_a_different_revision() -> None:
    run = ReviewRun("org-1", "repo-1", 42, "abc123")

    assert run.is_stale_for("def456")


@pytest.mark.parametrize("pull_request_number", [0, -1, True])
def test_review_run_rejects_invalid_pull_request_number(
    pull_request_number: int,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        ReviewRun("org-1", "repo-1", pull_request_number, "abc123")


def test_review_run_rejects_empty_revision() -> None:
    with pytest.raises(ValueError, match="revision"):
        ReviewRun("org-1", "repo-1", 42, " ")