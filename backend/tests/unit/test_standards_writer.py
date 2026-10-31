import asyncio

import pytest

from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)
from code_review_assistant.infrastructure.database.standards_writer import (
    SqlAlchemyStandardsWriter,
)


class FakeSession:
    def __init__(self) -> None:
        self.added_records: list[StandardRecord] = []

    def add_all(self, records: list[StandardRecord]) -> None:
        self.added_records.extend(records)


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSessionFactory:
    def __init__(self) -> None:
        self.session = FakeSession()
        self.begin_calls = 0

    def begin(self) -> FakeSessionContext:
        self.begin_calls += 1
        return FakeSessionContext(self.session)


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
        severity=Severity.MEDIUM,
    )


def test_writer_maps_standard_into_organization_record() -> None:
    session_factory = FakeSessionFactory()
    writer = SqlAlchemyStandardsWriter(session_factory)

    asyncio.run(writer.add_many("org-1", (make_standard(),)))

    assert session_factory.begin_calls == 1
    assert len(session_factory.session.added_records) == 1

    record = session_factory.session.added_records[0]
    assert record.organization_id == "org-1"
    assert record.standard_id == "ORG-CS-01"
    assert record.version == "1"
    assert record.category == "reliability"
    assert record.severity == "medium"
    assert record.enforcement == "mandatory"


@pytest.mark.parametrize(
    ("organization_id", "standards", "message"),
    [
        (" ", (make_standard(),), "organization_id"),
        ("org-1", (), "non-empty tuple"),
        ("org-1", ("not a standard",), "Standard objects"),
    ],
)
def test_writer_rejects_invalid_input(
    organization_id: str,
    standards: tuple[Standard, ...] | tuple[str, ...],
    message: str,
) -> None:
    session_factory = FakeSessionFactory()
    writer = SqlAlchemyStandardsWriter(session_factory)

    with pytest.raises(ValueError, match=message):
        asyncio.run(writer.add_many(organization_id, standards))  # type: ignore[arg-type]

    assert session_factory.begin_calls == 0