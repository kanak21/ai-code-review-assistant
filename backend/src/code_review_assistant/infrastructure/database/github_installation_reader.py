from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.ports.github_installation_reader import (
    GitHubInstallationReader,
)
from code_review_assistant.infrastructure.database.github_installation_record import (
    GitHubInstallationRecord,
)


class SqlAlchemyGitHubInstallationReader(GitHubInstallationReader):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_installation_id(self, organization_id: str) -> int:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must not be empty")

        statement = select(GitHubInstallationRecord.installation_id).where(
            GitHubInstallationRecord.organization_id == organization_id
        )

        async with self._session_factory() as session:
            installation_id = await session.scalar(statement)

        if installation_id is None:
            raise LookupError(
                f"No GitHub App installation is registered for organization "
                f"{organization_id!r}"
            )

        return installation_id