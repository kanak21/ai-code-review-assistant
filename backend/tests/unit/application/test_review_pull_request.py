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
from code_review_assistant.infrastructure.analysis.csharp_standards_analyzer import (
    CSharpStandardsAnalyzer,
)
from code_review_assistant.application.services.retrieve_relevant_standards import (
    RetrieveRelevantStandards,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock

from code_review_assistant.infrastructure.llm.anthropic_review_analyzer import (
    AnthropicReviewAnalyzer,
)


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
        category="reliability",
        severity=Severity.MEDIUM
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


def test_review_workflow_reports_demo_blocking_async_finding() -> None:
    run = ReviewRun("demo-org", "demo-repo", 1, "revision-1")
    changed_file = ChangedFile(
        path="src/Example.cs",
        kind=ChangeKind.MODIFIED,
        additions=1,
        deletions=1,
        patch="@@ -1 +1 @@\n-await task;\n+var value = task.Result;\n",
    )
    standard = Standard(
        standard_id="DEMO-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="Fictional demo standards",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )
    use_case = ReviewPullRequest(
        FakePullRequestReader((changed_file,)),
        FakeStandardsReader((standard,)),
        CSharpStandardsAnalyzer(),
    )

    result = asyncio.run(use_case.execute(run))

    assert result.run == run
    assert result.coverage.status is CoverageStatus.COMPLETE
    assert len(result.findings) == 1
    assert result.findings[0].standard_id == "DEMO-CS-02"
    assert result.findings[0].file_path == "src/Example.cs"
    assert result.findings[0].start_line == 1
    assert result.findings[0].evidence == "var value = task.Result;"


def test_review_workflow_uses_retrieved_standards() -> None:
    run = make_run()
    changed_files = (make_file("src/example.cs"),)
    mandatory = make_standard()
    relevant = Standard(
        standard_id="ORG-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="engineering/csharp.md",
        enforcement=Enforcement.RECOMMENDED,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )

    class FakeEmbeddingStore:
        async def list_mandatory_standards(
            self,
            organization_id: str,
            language: str,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            return (mandatory,)

        async def find_similar_standards(
            self,
            organization_id: str,
            language: str,
            embedding_model: str,
            query_vector: tuple[float, ...],
            limit: int,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            assert embedding_model == "test-embedding-model"
            assert len(query_vector) == 1536
            assert limit == 5
            return (relevant,)

    class FakeEmbedder:
        model = "test-embedding-model"
        dimensions = 1536

        async def embed(
            self,
            texts: tuple[str, ...],
        ) -> tuple[tuple[float, ...], ...]:
            assert len(texts) == 1
            return ((1.0,) + (0.0,) * 1535,)

    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(),
        checks=(),
    )
    analyzer = FakeReviewAnalyzer(analysis)
    workflow = ReviewPullRequest(
        FakePullRequestReader(changed_files),
        RetrieveRelevantStandards(FakeEmbeddingStore(), FakeEmbedder()),
        analyzer,
    )

    result = asyncio.run(workflow.execute(run))

    assert analyzer.received_standards == (mandatory, relevant)
    assert result.findings == ()


def test_review_workflow_passes_retrieved_standards_to_analyzer() -> None:
    run = make_run()
    changed_files = (make_file("src/example.cs"),)
    mandatory = make_standard()
    relevant = Standard(
        standard_id="ORG-CS-02",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="engineering/csharp.md",
        enforcement=Enforcement.RECOMMENDED,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )

    class FakeEmbeddingStore:
        async def list_mandatory_standards(
            self,
            organization_id: str,
            language: str,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            return (mandatory,)

        async def find_similar_standards(
            self,
            organization_id: str,
            language: str,
            embedding_model: str,
            query_vector: tuple[float, ...],
            limit: int,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            assert embedding_model == "test-embedding-model"
            assert len(query_vector) == 1536
            assert limit == 5
            return (relevant,)

    class FakeEmbedder:
        model = "test-embedding-model"
        dimensions = 1536

        async def embed(
            self,
            texts: tuple[str, ...],
        ) -> tuple[tuple[float, ...], ...]:
            assert len(texts) == 1
            return ((1.0,) + (0.0,) * 1535,)

    analysis = ReviewAnalysis(
        analyzed_paths=("src/example.cs",),
        findings=(),
        checks=(),
    )
    analyzer = FakeReviewAnalyzer(analysis)
    workflow = ReviewPullRequest(
        FakePullRequestReader(changed_files),
        RetrieveRelevantStandards(FakeEmbeddingStore(), FakeEmbedder()),
        analyzer,
    )

    result = asyncio.run(workflow.execute(run))

    assert analyzer.received_standards == (mandatory, relevant)
    assert result.findings == ()


def test_review_workflow_with_rag_and_mocked_anthropic() -> None:
    run = make_run()
    changed_file = make_file("src/example.cs")
    standard = make_standard()

    class FakeEmbeddingStore:
        async def list_mandatory_standards(
            self,
            organization_id: str,
            language: str,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            return (standard,)

        async def find_similar_standards(
            self,
            organization_id: str,
            language: str,
            embedding_model: str,
            query_vector: tuple[float, ...],
            limit: int,
        ) -> tuple[Standard, ...]:
            assert organization_id == run.organization_id
            assert language == "csharp"
            assert embedding_model == "test-embedding-model"
            assert len(query_vector) == 1536
            assert limit == 5
            return ()

    class FakeEmbedder:
        model = "test-embedding-model"
        dimensions = 1536

        async def embed(
            self,
            texts: tuple[str, ...],
        ) -> tuple[tuple[float, ...], ...]:
            assert len(texts) == 1
            return ((1.0,) + (0.0,) * 1535,)

    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="submit_review",
                    input={
                        "findings": [
                            {
                                "rule_id": "AI-001",
                                "standard_id": standard.standard_id,
                                "severity": "medium",
                                "title": "Review finding",
                                "rationale": "This added line violates the standard.",
                                "file_path": "src/example.cs",
                                "start_line": 2,
                                "end_line": 2,
                                "evidence": "new",
                            }
                        ]
                    },
                )
            ]
        )
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))

    retrieval = RetrieveRelevantStandards(FakeEmbeddingStore(), FakeEmbedder())
    analyzer = AnthropicReviewAnalyzer(client, model="test-model")
    workflow = ReviewPullRequest(
        FakePullRequestReader((changed_file,)),
        retrieval,
        analyzer,
    )

    result = asyncio.run(workflow.execute(run))

    assert result.coverage.status is CoverageStatus.COMPLETE
    assert len(result.findings) == 1
    assert result.findings[0].standard_id == standard.standard_id
    assert result.findings[0].file_path == "src/example.cs"
    assert result.findings[0].start_line == 2
    assert result.findings[0].evidence == "new"
    create.assert_awaited_once()