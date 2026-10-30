import pytest

from code_review_assistant.domain.models.review_coverage import (
    CoverageStatus,
    ReviewCoverage,
)


@pytest.mark.parametrize(
    ("changed", "analyzed", "expected_status", "expected_percentage"),
    [
        (0, 0, CoverageStatus.NO_CHANGES, None),
        (4, 0, CoverageStatus.NOT_STARTED, 0.0),
        (5, 2, CoverageStatus.PARTIAL, 40.0),
        (3, 3, CoverageStatus.COMPLETE, 100.0),
    ],
)
def test_coverage_reports_status_and_percentage(
    changed: int,
    analyzed: int,
    expected_status: CoverageStatus,
    expected_percentage: float | None,
) -> None:
    coverage = ReviewCoverage(changed, analyzed)

    assert coverage.status is expected_status
    assert coverage.percentage == expected_percentage


def test_coverage_rejects_analyzed_count_above_changed_count() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        ReviewCoverage(changed_files=2, analyzed_files=3)


def test_coverage_rejects_boolean_count() -> None:
    with pytest.raises(ValueError, match="integer"):
        ReviewCoverage(changed_files=True, analyzed_files=0)