import asyncio
from types import SimpleNamespace
from typing import Any

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)
from code_review_assistant.infrastructure.database.standards_reader import (
    SqlAlchemyStandardsReader,
)


class FakeScalarResult:
    def __init__(self, records: list[StandardRecord]) -> None:
        self.records = records

    def all(self) -> list[StandardRecord]:
        return self.records


class FakeSession:
    def __init__(self, records: list[StandardRecord]) -> None:
        self.records = records
        self.statement: Any | None = None

    async def scalars(self, statement: Any) -> FakeScalarResult:
        self.statement = statement
        return FakeScalarResult(self.records)


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, records: list[StandardRecord]) -> None:
        self.session = FakeSession(records)
        self.calls = 0

    def __call__(self) -> FakeSessionContext:
        self.calls += 1
        return FakeSessionContext(self.session)


def make_standard_record() -> StandardRecord:
    return StandardRecord(
        organization_id="org-1",
        standard_id="ORG-CS-01",
        version="1",
        title="Propagate cancellation",
        guidance="Pass cancellation tokens to asynchronous calls.",
        source="engineering/csharp.md",
        enforcement="mandatory",
        language="csharp",
        category="reliability",
        severity="medium",
        is_active=True,
    )


def test_reader_filters_by_organization_and_maps_standard() -> None:
    session_factory = FakeSessionFactory([make_standard_record()])
    reader = SqlAlchemyStandardsReader(session_factory)
    run = ReviewRun("org-1", "repo-1", 42, "abc123")
    files = (ChangedFile("src/example.cs", ChangeKind.MODIFIED, 1, 0),)

    standards = asyncio.run(reader.get_applicable_standards(run, files))

    assert len(standards) == 1
    assert standards[0].standard_id == "ORG-CS-01"
    assert standards[0].category == "reliability"
    assert standards[0].severity.value == "medium"

    compiled = session_factory.session.statement.compile()
    assert "org-1" in compiled.params.values()
    assert "csharp" in compiled.params.values()
    assert "standards.is_active IS true" in str(compiled)
    

def test_reader_skips_database_for_non_csharp_changes() -> None:
    session_factory = FakeSessionFactory([make_standard_record()])
    reader = SqlAlchemyStandardsReader(session_factory)
    run = ReviewRun("org-1", "repo-1", 42, "abc123")
    files = (ChangedFile("README.md", ChangeKind.MODIFIED, 1, 0),)

    standards = asyncio.run(reader.get_applicable_standards(run, files))

    assert standards == ()
    assert session_factory.calls == 0