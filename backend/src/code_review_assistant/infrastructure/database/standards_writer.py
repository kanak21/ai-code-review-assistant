from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.domain.models.standard import Standard
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)


class SqlAlchemyStandardsWriter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def add_many(
        self,
        organization_id: str,
        standards: tuple[Standard, ...],
    ) -> None:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must not be empty")

        if not isinstance(standards, tuple) or not standards:
            raise ValueError("standards must be a non-empty tuple")

        if not all(isinstance(standard, Standard) for standard in standards):
            raise ValueError("standards must contain Standard objects")

        records = [
            StandardRecord(
                organization_id=organization_id,
                standard_id=standard.standard_id,
                version=standard.version,
                title=standard.title,
                guidance=standard.guidance,
                source=standard.source,
                enforcement=standard.enforcement.value,
                language=standard.language,
                category=standard.category,
                severity=standard.severity.value,
            )
            for standard in standards
        ]

        async with self._session_factory.begin() as session:
            session.add_all(records)