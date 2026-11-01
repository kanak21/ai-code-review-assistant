from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import delete

from code_review_assistant.application.ports.github_installation_writer import (
    GitHubInstallationWriter,
)
from code_review_assistant.infrastructure.database.github_installation_record import (
    GitHubInstallationRecord,
)


class SqlAlchemyGitHubInstallationWriter(GitHubInstallationWriter):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def register(
        self,
        organization_id: str,
        installation_id: int,
    ) -> None:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must not be empty")
        if (
            not isinstance(installation_id, int)
            or isinstance(installation_id, bool)
            or installation_id < 1
        ):
            raise ValueError("installation_id must be a positive integer")

        statement = insert(GitHubInstallationRecord).values(
            organization_id=organization_id,
            installation_id=installation_id,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[GitHubInstallationRecord.organization_id],
            set_={"installation_id": statement.excluded.installation_id},
        )

        async with self._session_factory.begin() as session:
            await session.execute(statement)

    async def remove(self, installation_id: int) -> None:
        if (
            not isinstance(installation_id, int)
            or isinstance(installation_id, bool)
            or installation_id < 1
        ):
            raise ValueError("installation_id must be a positive integer")

        async with self._session_factory.begin() as session:
            await session.execute(
                delete(GitHubInstallationRecord).where(
                    GitHubInstallationRecord.installation_id == installation_id
                )
            )