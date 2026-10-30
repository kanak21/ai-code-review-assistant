import pytest

from code_review_assistant.domain.models.check_result import (
    CheckResult,
    CheckStatus,
)


@pytest.mark.parametrize("status", list(CheckStatus))
def test_check_result_preserves_each_status(status: CheckStatus) -> None:
    result = CheckResult("unit-tests", status, "Check outcome")

    assert result.status is status


def test_check_result_rejects_empty_check_id() -> None:
    with pytest.raises(ValueError, match="check_id"):
        CheckResult(" ", CheckStatus.PASSED, "Tests passed")


def test_check_result_rejects_empty_summary() -> None:
    with pytest.raises(ValueError, match="summary"):
        CheckResult("unit-tests", CheckStatus.FAILED, " ")