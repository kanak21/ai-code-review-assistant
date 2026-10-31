from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.domain.models.changed_file import ChangedFile
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)


class SqlAlchemyStandardsReader:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_applicable_standards(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
    ) -> tuple[Standard, ...]:
        if not isinstance(run, ReviewRun):
            raise ValueError("run must be a ReviewRun")

        if not isinstance(changed_files, tuple) or not all(
            isinstance(file, ChangedFile) for file in changed_files
        ):
            raise ValueError("changed_files must be a tuple of ChangedFile objects")

        has_csharp_files = any(
            file.path.casefold().endswith(".cs")
            for file in changed_files
        )
        if not has_csharp_files:
            return ()

        statement = (
            select(StandardRecord)
            .where(
                StandardRecord.organization_id == run.organization_id,
                StandardRecord.language == "csharp",
                StandardRecord.is_active.is_(True),
            )
            .order_by(StandardRecord.standard_id, StandardRecord.version)
        )

        async with self._session_factory() as session:
            records = (await session.scalars(statement)).all()

        return tuple(
            Standard(
                standard_id=record.standard_id,
                version=record.version,
                title=record.title,
                guidance=record.guidance,
                source=record.source,
                enforcement=Enforcement(record.enforcement),
                language=record.language,
                category=record.category,
                severity=Severity(record.severity),
            )
            for record in records
        )