import asyncio
import os
from uuid import uuid4

import pytest

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)
from code_review_assistant.infrastructure.database.standards_reader import (
    SqlAlchemyStandardsReader,
)
from code_review_assistant.infrastructure.database.standards_writer import (
    SqlAlchemyStandardsWriter,
)
from code_review_assistant.settings import Settings


def test_standards_write_and_read_from_postgres() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"integration-test-{uuid4().hex}"
    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    standard = Standard(
        standard_id="ORG-CS-TEST-01",
        version="1",
        title="Integration test standard",
        guidance="Test standard persistence.",
        source="integration-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.MEDIUM,
    )
    run = ReviewRun(organization_id, "repo-test", 1, "revision-test")
    changed_files = (
        ChangedFile("src/example.cs", ChangeKind.MODIFIED, 1, 0),
    )

    async def verify_persistence() -> None:
        try:
            writer = SqlAlchemyStandardsWriter(session_factory)
            await writer.add_many(organization_id, (standard,))

            reader = SqlAlchemyStandardsReader(session_factory)
            result = await reader.get_applicable_standards(run, changed_files)

            assert result == (standard,)
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_persistence(),
        loop_factory=asyncio.SelectorEventLoop,
    )