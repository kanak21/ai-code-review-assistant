import math

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.models.standard_embedding import (
    StandardEmbedding,
    StandardEmbeddingDocument,
)
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.database.standard_embedding_record import (
    StandardEmbeddingRecord,
)
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)


class SqlAlchemyStandardEmbeddingStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def list_active_standards(
        self,
        organization_id: str,
    ) -> tuple[StandardEmbeddingDocument, ...]:
        self._validate_organization_id(organization_id)

        statement = (
            select(
                StandardRecord.id,
                StandardRecord.standard_id,
                StandardRecord.version,
                StandardRecord.title,
                StandardRecord.guidance,
                StandardRecord.source,
                StandardRecord.language,
                StandardRecord.category,
            )
            .where(
                StandardRecord.organization_id == organization_id,
                StandardRecord.is_active.is_(True),
            )
            .order_by(StandardRecord.id)
        )

        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        return tuple(StandardEmbeddingDocument(*row) for row in rows)

    async def get_content_hashes(
        self,
        organization_id: str,
        standard_record_ids: tuple[int, ...],
        embedding_model: str,
    ) -> dict[int, str]:
        self._validate_organization_id(organization_id)
        self._validate_model(embedding_model)
        if not standard_record_ids:
            return {}

        statement = (
            select(
                StandardEmbeddingRecord.standard_record_id,
                StandardEmbeddingRecord.content_hash,
            )
            .join(
                StandardRecord,
                StandardRecord.id == StandardEmbeddingRecord.standard_record_id,
            )
            .where(
                StandardRecord.organization_id == organization_id,
                StandardRecord.is_active.is_(True),
                StandardEmbeddingRecord.standard_record_id.in_(standard_record_ids),
                StandardEmbeddingRecord.embedding_model == embedding_model,
            )
        )

        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()

        return {record_id: content_hash for record_id, content_hash in rows}

    async def upsert_embeddings(
        self,
        organization_id: str,
        embedding_model: str,
        embeddings: tuple[StandardEmbedding, ...],
    ) -> None:
        self._validate_organization_id(organization_id)
        self._validate_model(embedding_model)

        if not isinstance(embeddings, tuple) or not embeddings:
            raise ValueError("embeddings must be a non-empty tuple")
        if not all(isinstance(item, StandardEmbedding) for item in embeddings):
            raise ValueError("embeddings must contain StandardEmbedding objects")

        record_ids = tuple(item.standard_record_id for item in embeddings)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("embeddings must not contain duplicate standard IDs")

        for item in embeddings:
            if (
                not item.vector
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for value in item.vector
                )
            ):
                raise ValueError("each embedding must be a non-empty finite vector")
            if len(item.content_hash) != 64:
                raise ValueError("content_hash must be a 64-character SHA-256 hash")

        async with self._session_factory.begin() as session:
            owned_ids = set(
                (
                    await session.scalars(
                        select(StandardRecord.id)
                        .where(
                            StandardRecord.organization_id == organization_id,
                            StandardRecord.is_active.is_(True),
                            StandardRecord.id.in_(record_ids),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            if owned_ids != set(record_ids):
                raise ValueError(
                    "all embedding records must be active standards "
                    "belonging to the organization"
                )

            statement = insert(StandardEmbeddingRecord).values(
                [
                    {
                        "standard_record_id": item.standard_record_id,
                        "embedding_model": embedding_model,
                        "content_hash": item.content_hash,
                        "embedding": list(item.vector),
                    }
                    for item in embeddings
                ]
            )
            statement = statement.on_conflict_do_update(
                index_elements=[
                    StandardEmbeddingRecord.standard_record_id,
                    StandardEmbeddingRecord.embedding_model,
                ],
                set_={
                    "content_hash": statement.excluded.content_hash,
                    "embedding": statement.excluded.embedding,
                },
            )
            await session.execute(statement)

    async def find_similar_standards(
        self,
        organization_id: str,
        language: str,
        embedding_model: str,
        query_vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Standard, ...]:
        self._validate_organization_id(organization_id)
        self._validate_model(embedding_model)

        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must not be empty")
        if (
            not isinstance(query_vector, tuple)
            or not query_vector
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in query_vector
            )
        ):
            raise ValueError("query_vector must be a non-empty finite tuple")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        distance = StandardEmbeddingRecord.embedding.cosine_distance(
            list(query_vector)
        )
        statement = (
            select(StandardRecord)
            .join(
                StandardEmbeddingRecord,
                StandardEmbeddingRecord.standard_record_id == StandardRecord.id,
            )
            .where(
                StandardRecord.organization_id == organization_id,
                StandardRecord.language == language,
                StandardRecord.is_active.is_(True),
                StandardEmbeddingRecord.embedding_model == embedding_model,
            )
            .order_by(distance, StandardRecord.id)
            .limit(limit)
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

    async def list_mandatory_standards(
        self,
        organization_id: str,
        language: str,
    ) -> tuple[Standard, ...]:
        self._validate_organization_id(organization_id)
        if not isinstance(language, str) or not language.strip():
            raise ValueError("language must not be empty")

        statement = (
            select(StandardRecord)
            .where(
                StandardRecord.organization_id == organization_id,
                StandardRecord.language == language,
                StandardRecord.is_active.is_(True),
                StandardRecord.enforcement == Enforcement.MANDATORY.value,
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

    @staticmethod
    def _validate_organization_id(organization_id: str) -> None:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must not be empty")

    @staticmethod
    def _validate_model(embedding_model: str) -> None:
        if not isinstance(embedding_model, str) or not embedding_model.strip():
            raise ValueError("embedding_model must not be empty")