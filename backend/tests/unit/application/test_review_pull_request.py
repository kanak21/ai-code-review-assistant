import asyncio

import pytest

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult, CheckStatus
from code_review_assistant.domain.models.review_coverage import CoverageStatus
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.application.services.review_pull_request import ReviewPullRequest


def make_run() -> ReviewRun:
    return ReviewRun("org-1", "repo-1", 42, "abc123")


def make_file(path: str) -> ChangedFile:
    return ChangedFile(
        path=path,
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1,2 +1,2 @@\n context\n-old\n+new\n",
    )


def make_standard() -> Standard:
    return Standard(
        standard_id="ORG-CS-01",
        version="1",
        title="Propagate cancellation",
        guidance="Pass cancellation tokens to asynchronous calls.",
        source="engineering/csharp.md",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
    )


def make_finding(
    path: str = "src/example.cs",
    standard_id: str | None = "ORG-CS-01",
) -> ReviewFinding:
    return ReviewFinding(
        rule_id="CS001",
        severity=Severity.MEDIUM,
        title="Propagate cancellation",
        rationale="Pass cancellation tokens to asynchronous calls.",
        file_path=path,
        start_line=2,
        end_line=2,
        evidence="await client.GetAsync(url);",
        standard_id=standard_id,
    )


class FakePullRequestReader:
    def __init__(self, files: tuple[ChangedFile, ...]) -> None:
        self.files = files
        self.received_run: ReviewRun | None = None

    async def fetch_changed_files(
        self,
        run: ReviewRun,
    ) -> tuple[ChangedFile, ...]:
        self.received_run = run
        return self.files


class FakeStandardsReader:
    def __init__(self, standards: tuple[Standard, ...]) -> None:
        self.standards = standards
        self.received_run: ReviewRun | None = None
        self.received_files: tuple[ChangedFile, ...] | None = None

    async def get_applicable_standards(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
    ) -> tuple[Standard, ...]:
        self.received_run = run
        self.received_files = changed_files
        return self.standards


class FakeReviewAnalyzer:
    def __init__(self, analysis: ReviewAnalysis) -> None:
        self.analysis = analysis
        self.received_run: ReviewRun | None = None
        self.received_files: tuple[ChangedFile, ...] | None = None
        self.received_standards: tuple[Standard, ...] | None = None

    async def analyze(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
        standards: tuple[Standard, ...],
    ) -> ReviewAnalysis:
        self.received_run = run
        self.received_files = changed_files
        self.received_standards = standards
        return self.analysis


def make_use_case(
    files: tuple[ChangedFile, ...],
    standards: tuple[Standard, ...],
    analysis: ReviewAnalysis,
) -> tuple[ReviewPullRequest, FakePullRequestReader, FakeStandardsReader, FakeReviewAnalyzer]:
    pull_request_reader = FakePullRequestReader(files)
    standards_reader = FakeStandardsReader(standards)
    analyzer = FakeReviewAnalyzer(analysis)

    return (
        ReviewPullRequest(pull_request_reader, standards_reader, analyzer),
        pull_request_reader,
        standards_reader,
        analyzer,
    )


def test_review_use_case_calls_ports_and_returns_result() -> None:
    run = make_run()
    files = (make_file("src/example.cs"),)
    standards = (make_standard(),)
    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(make_finding(),),
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
    )
    use_case, reader, standards_reader, analyzer = make_use_case(
        files, standards, analysis
    )

    result = asyncio.run(use_case.execute(run))

    assert result.run == run
    assert result.changed_files == files
    assert result.findings == analysis.findings
    assert result.checks == analysis.checks
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert reader.received_run == run
    assert standards_reader.received_run == run
    assert standards_reader.received_files == files
    assert analyzer.received_run == run
    assert analyzer.received_files == files
    assert analyzer.received_standards == standards


def test_partial_analysis_reports_partial_coverage() -> None:
    files = (
        make_file("src/example.cs"),
        make_file("src/other.cs"),
    )
    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(),
        checks=(),
    )
    use_case, _, _, _ = make_use_case(files, (), analysis)

    result = asyncio.run(use_case.execute(make_run()))

    assert result.coverage.status is CoverageStatus.PARTIAL
    assert result.coverage.analyzed_files == 1
    assert result.coverage.changed_files == 2


def test_rejects_analyzer_path_not_in_pull_request() -> None:
    analysis = ReviewAnalysis(
        analyzed_paths=("src/not-in-pr.cs",),
        findings=(),
        checks=(),
    )
    use_case, _, _, _ = make_use_case(
        (make_file("src/example.cs"),), (), analysis
    )

    with pytest.raises(ValueError, match="outside the pull request"):
        asyncio.run(use_case.execute(make_run()))


def test_rejects_finding_that_cites_unsupplied_standard() -> None:
    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(make_finding(standard_id="ORG-CS-UNKNOWN"),),
        checks=(),
    )
    use_case, _, _, _ = make_use_case(
        (make_file("src/example.cs"),), (make_standard(),), analysis
    )

    with pytest.raises(ValueError, match="standard not supplied"):
        asyncio.run(use_case.execute(make_run()))