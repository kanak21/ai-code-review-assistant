import asyncio

from code_review_assistant.application.ports.standards_reader import StandardsReader
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard


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


def test_standards_reader_accepts_provider_independent_implementation() -> None:
    run = ReviewRun("org-1", "repo-1", 42, "abc123")
    changed_files = (
        ChangedFile("src/example.cs", ChangeKind.MODIFIED, 1, 0),
    )
    standards = (
        Standard(
            standard_id="ORG-CS-01",
            version="1",
            title="Propagate cancellation",
            guidance="Pass cancellation tokens to asynchronous operations.",
            source="engineering/csharp.md",
            enforcement=Enforcement.MANDATORY,
            language="csharp",
            category="reliability",
            severity=Severity.MEDIUM
        ),
    )
    reader: StandardsReader = FakeStandardsReader(standards)

    result = asyncio.run(
        reader.get_applicable_standards(run, changed_files)
    )

    assert result == standards
    assert isinstance(reader, FakeStandardsReader)
    assert reader.received_run == run
    assert reader.received_files == changed_files