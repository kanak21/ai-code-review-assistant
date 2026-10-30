import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult, CheckStatus
from code_review_assistant.domain.models.review_coverage import ReviewCoverage
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.review_result import ReviewResult
from code_review_assistant.domain.models.review_run import ReviewRun


def make_file(path: str = "src/changed.cs") -> ChangedFile:
    return ChangedFile(
        path,
        ChangeKind.MODIFIED,
        1,
        1,
        patch="@@ -1,2 +1,2 @@\n context\n-old\n+new\n",
    )


def make_finding(
    path: str = "src/changed.cs",
    start_line: int = 2,
    end_line: int = 2,
) -> ReviewFinding:
    return ReviewFinding(
        "CS001", Severity.MEDIUM, "Title", "Rationale",
        path, start_line, end_line, "code evidence",
    )


def make_result(
    files: tuple[ChangedFile, ...] = (make_file(),),
    findings: tuple[ReviewFinding, ...] = (make_finding(),),
    coverage: ReviewCoverage = ReviewCoverage(1, 1),
) -> ReviewResult:
    return ReviewResult(
        run=ReviewRun("org-1", "repo-1", 42, "abc123"),
        changed_files=files,
        findings=findings,
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
        coverage=coverage,
    )


def test_review_result_accepts_consistent_data() -> None:
    result = make_result()

    assert result.findings[0].file_path == result.changed_files[0].path


def test_review_result_rejects_finding_on_unchanged_file() -> None:
    with pytest.raises(ValueError, match="changed file"):
        make_result(findings=(make_finding("src/other.cs"),))


def test_review_result_rejects_duplicate_file_paths() -> None:
    with pytest.raises(ValueError, match="unique"):
        make_result(files=(make_file(), make_file()))


def test_review_result_rejects_mismatched_coverage() -> None:
    with pytest.raises(ValueError, match="match changed files"):
        make_result(coverage=ReviewCoverage(2, 1))