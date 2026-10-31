import asyncio

import pytest

from code_review_assistant.application.models.review_analysis import ReviewAnalysis
from code_review_assistant.application.ports.review_analyzer import ReviewAnalyzer
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.check_result import CheckResult, CheckStatus
from code_review_assistant.domain.models.review_finding import ReviewFinding, Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard


def make_finding() -> ReviewFinding:
    return ReviewFinding(
        rule_id="CS001",
        severity=Severity.MEDIUM,
        title="Propagate cancellation",
        rationale="Pass cancellation tokens to asynchronous calls.",
        file_path="src/example.cs",
        start_line=2,
        end_line=2,
        evidence="await client.GetAsync(url);",
        standard_id="ORG-CS-01",
    )


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


def test_analyzer_port_accepts_provider_independent_implementation() -> None:
    run = ReviewRun("org-1", "repo-1", 42, "abc123")
    files = (ChangedFile("src/example.cs", ChangeKind.MODIFIED, 1, 0),)
    standards = (
        Standard(
            standard_id="ORG-CS-01",
            version="1",
            title="Propagate cancellation",
            guidance="Pass cancellation tokens to asynchronous calls.",
            source="engineering/csharp.md",
            enforcement=Enforcement.MANDATORY,
            language="csharp",
            category="reliability",
            severity=Severity.MEDIUM
        ),
    )
    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(make_finding(),),
        checks=(CheckResult("tests", CheckStatus.NOT_RUN, "Not run"),),
    )
    analyzer: ReviewAnalyzer = FakeReviewAnalyzer(analysis)

    result = asyncio.run(analyzer.analyze(run, files, standards))

    assert result == analysis
    assert isinstance(analyzer, FakeReviewAnalyzer)
    assert analyzer.received_run == run
    assert analyzer.received_files == files
    assert analyzer.received_standards == standards


def test_review_analysis_rejects_duplicate_analyzed_paths() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        ReviewAnalysis(
            analyzed_paths=("src/example.cs", "src/example.cs"),
            findings=(),
            checks=(),
        )