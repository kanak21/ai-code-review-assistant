import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.github_installation_reader import (
    SqlAlchemyGitHubInstallationReader,
)
from code_review_assistant.infrastructure.database.github_installation_record import (
    GitHubInstallationRecord,
)
from code_review_assistant.infrastructure.database.github_installation_writer import (
    SqlAlchemyGitHubInstallationWriter,
)
from code_review_assistant.settings import Settings


def test_github_installation_reader_reads_registered_mapping() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"github-install-test-{uuid4().hex}"
    settings = Settings().model_copy(update={"postgres_db": "review_assistant_test"})
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    async def verify_reader() -> None:
        try:
            reader = SqlAlchemyGitHubInstallationReader(session_factory)
            writer = SqlAlchemyGitHubInstallationWriter(session_factory)

            await writer.register(organization_id, 987654321)
            assert await reader.get_installation_id(organization_id) == 987654321

            await writer.register(organization_id, 987654322)
            assert await reader.get_installation_id(organization_id) == 987654322

            await writer.remove(987654322)
            with pytest.raises(LookupError, match="No GitHub App installation"):
                await reader.get_installation_id(organization_id)

            with pytest.raises(LookupError, match="No GitHub App installation"):
                await reader.get_installation_id(f"missing-{organization_id}")
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(GitHubInstallationRecord).where(
                        GitHubInstallationRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(
        verify_reader(),
        loop_factory=asyncio.SelectorEventLoop,
    )