import asyncio
import hashlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from code_review_assistant.application.models.standard_embedding import (
    StandardEmbedding,
)
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.infrastructure.database.engine import (
    create_database_engine,
    create_session_factory,
)
from code_review_assistant.infrastructure.database.standard_embedding_record import (
    StandardEmbeddingRecord,
)
from code_review_assistant.infrastructure.database.standard_embedding_store import (
    SqlAlchemyStandardEmbeddingStore,
)
from code_review_assistant.infrastructure.database.standard_record import (
    StandardRecord,
)
from code_review_assistant.infrastructure.database.standards_writer import (
    SqlAlchemyStandardsWriter,
)
from code_review_assistant.settings import Settings
from code_review_assistant.application.services.retrieve_relevant_standards import (
    RetrieveRelevantStandards,
)
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.application.services.index_standards import IndexStandards


def test_embedding_store_is_organization_scoped_and_persists_vectors() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    organization_id = f"embedding-test-{uuid4().hex}"
    other_organization_id = f"other-{uuid4().hex}"
    model = "test-embedding-model"
    content_hash = hashlib.sha256(b"integration test content").hexdigest()

    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    standard = Standard(
        standard_id="ORG-CS-EMBED-TEST",
        version="1",
        title="Embedding store integration test",
        guidance="Temporary standard for testing vector persistence.",
        source="integration-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.MEDIUM,
    )

    async def verify_store() -> None:
        try:
            await SqlAlchemyStandardsWriter(session_factory).add_many(
                organization_id,
                (standard,),
            )

            async with session_factory() as session:
                record_id = await session.scalar(
                    select(StandardRecord.id).where(
                        StandardRecord.organization_id == organization_id,
                        StandardRecord.standard_id == standard.standard_id,
                    )
                )

            assert record_id is not None

            store = SqlAlchemyStandardEmbeddingStore(session_factory)
            documents = await store.list_active_standards(organization_id)
            assert len(documents) == 1
            assert documents[0].standard_record_id == record_id
            assert documents[0].standard_id == standard.standard_id

            embedding = StandardEmbedding(
                standard_record_id=record_id,
                content_hash=content_hash,
                vector=(0.1,) * 768,
            )
            await store.upsert_embeddings(
                organization_id,
                model,
                (embedding,),
            )

            hashes = await store.get_content_hashes(
                organization_id,
                (record_id,),
                model,
            )
            assert hashes == {record_id: content_hash}

            with pytest.raises(ValueError, match="belonging to the organization"):
                await store.upsert_embeddings(
                    other_organization_id,
                    model,
                    (embedding,),
                )

            async with session_factory() as session:
                persisted_vector = await session.scalar(
                    select(StandardEmbeddingRecord.embedding).where(
                        StandardEmbeddingRecord.standard_record_id == record_id,
                        StandardEmbeddingRecord.embedding_model == model,
                    )
                )

            assert persisted_vector is not None
            assert len(persisted_vector) == 768
            assert persisted_vector[0] == pytest.approx(0.1)
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify_store(), loop_factory=asyncio.SelectorEventLoop)


def test_similarity_search_is_ranked_and_organization_scoped() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip(
            "Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests"
        )

    organization_id = f"similarity-test-{uuid4().hex}"
    other_organization_id = f"other-{uuid4().hex}"
    model = "test-embedding-model"

    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    def make_standard(standard_id: str, title: str) -> Standard:
        return Standard(
            standard_id=standard_id,
            version="1",
            title=title,
            guidance=f"Guidance for {title}.",
            source="integration-test",
            enforcement=Enforcement.RECOMMENDED,
            language="csharp",
            category="reliability",
            severity=Severity.MEDIUM,
        )

    standards = (
        make_standard("SIM-NEAREST", "Nearest rule"),
        make_standard("SIM-FARTHER", "Farther rule"),
    )
    other_standard = make_standard("SIM-OTHER-ORG", "Other organization rule")

    async def verify_search() -> None:
        try:
            writer = SqlAlchemyStandardsWriter(session_factory)
            await writer.add_many(organization_id, standards)
            await writer.add_many(other_organization_id, (other_standard,))

            async with session_factory() as session:
                rows = (
                    await session.execute(
                        select(
                            StandardRecord.organization_id,
                            StandardRecord.standard_id,
                            StandardRecord.id,
                        ).where(
                            StandardRecord.organization_id.in_(
                                (organization_id, other_organization_id)
                            )
                        )
                    )
                ).all()

            record_ids = {
                (org_id, standard_id): record_id
                for org_id, standard_id, record_id in rows
            }
            nearest_id = record_ids[(organization_id, "SIM-NEAREST")]
            farther_id = record_ids[(organization_id, "SIM-FARTHER")]
            other_id = record_ids[(other_organization_id, "SIM-OTHER-ORG")]

            vector_nearest = (1.0, 0.0) + (0.0,) * 1534
            vector_farther = (0.0, 1.0) + (0.0,) * 1534

            def embedding(record_id: int, vector: tuple[float, ...]) -> StandardEmbedding:
                content_hash = hashlib.sha256(
                    str(record_id).encode("utf-8")
                ).hexdigest()
                return StandardEmbedding(record_id, content_hash, vector)

            store = SqlAlchemyStandardEmbeddingStore(session_factory)
            await store.upsert_embeddings(
                organization_id,
                model,
                (
                    embedding(nearest_id, vector_nearest),
                    embedding(farther_id, vector_farther),
                ),
            )
            await store.upsert_embeddings(
                other_organization_id,
                model,
                (embedding(other_id, vector_nearest),),
            )

            results = await store.find_similar_standards(
                organization_id=organization_id,
                language="csharp",
                embedding_model=model,
                query_vector=vector_nearest,
                limit=2,
            )

            assert tuple(result.standard_id for result in results) == (
                "SIM-NEAREST",
                "SIM-FARTHER",
            )
            assert "SIM-OTHER-ORG" not in {
                result.standard_id for result in results
            }
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id.in_(
                            (organization_id, other_organization_id)
                        )
                    )
                )
            await engine.dispose()

    asyncio.run(verify_search(), loop_factory=asyncio.SelectorEventLoop)


def test_retrieval_service_combines_mandatory_and_similar_standards() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip(
            "Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests"
        )

    organization_id = f"retrieval-test-{uuid4().hex}"
    other_organization_id = f"other-{uuid4().hex}"
    model = "test-embedding-model"

    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    def make_standard(
        standard_id: str,
        enforcement: Enforcement,
    ) -> Standard:
        return Standard(
            standard_id=standard_id,
            version="1",
            title=f"Test {standard_id}",
            guidance=f"Guidance for {standard_id}.",
            source="integration-test",
            enforcement=enforcement,
            language="csharp",
            category="reliability",
            severity=Severity.MEDIUM,
        )

    mandatory = make_standard("RETR-MANDATORY", Enforcement.MANDATORY)
    similar = make_standard("RETR-SIMILAR", Enforcement.RECOMMENDED)
    foreign = make_standard("RETR-FOREIGN", Enforcement.RECOMMENDED)

    class FakeEmbedder:
        model = "test-embedding-model"
        dimensions = 1536

        async def embed(
            self,
            texts: tuple[str, ...],
        ) -> tuple[tuple[float, ...], ...]:
            assert len(texts) == 1
            return ((1.0,) + (0.0,) * 1535,)

    async def verify_retrieval() -> None:
        try:
            writer = SqlAlchemyStandardsWriter(session_factory)
            await writer.add_many(organization_id, (mandatory, similar))
            await writer.add_many(other_organization_id, (foreign,))

            async with session_factory() as session:
                rows = (
                    await session.execute(
                        select(
                            StandardRecord.organization_id,
                            StandardRecord.standard_id,
                            StandardRecord.id,
                        ).where(
                            StandardRecord.organization_id.in_(
                                (organization_id, other_organization_id)
                            )
                        )
                    )
                ).all()

            record_ids = {
                (org_id, standard_id): record_id
                for org_id, standard_id, record_id in rows
            }

            store = SqlAlchemyStandardEmbeddingStore(session_factory)
            vector = (1.0,) + (0.0,) * 1535
            content_hash = hashlib.sha256(b"test").hexdigest()

            await store.upsert_embeddings(
                organization_id,
                model,
                (
                    StandardEmbedding(
                        record_ids[(organization_id, "RETR-SIMILAR")],
                        content_hash,
                        vector,
                    ),
                ),
            )
            await store.upsert_embeddings(
                other_organization_id,
                model,
                (
                    StandardEmbedding(
                        record_ids[(other_organization_id, "RETR-FOREIGN")],
                        content_hash,
                        vector,
                    ),
                ),
            )

            service = RetrieveRelevantStandards(store, FakeEmbedder())
            results = await service.execute(
                ReviewRun(organization_id, "repo-test", 1, "revision-test"),
                (
                    ChangedFile(
                        "src/example.cs",
                        ChangeKind.MODIFIED,
                        1,
                        0,
                        patch="@@ -1 +1 @@\n-old\n+new\n",
                    ),
                ),
            )

            result_ids = {standard.standard_id for standard in results}
            assert result_ids == {"RETR-MANDATORY", "RETR-SIMILAR"}
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id.in_(
                            (organization_id, other_organization_id)
                        )
                    )
                )
            await engine.dispose()

    asyncio.run(verify_retrieval(), loop_factory=asyncio.SelectorEventLoop)


def test_mock_indexing_then_retrieval_uses_test_database() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip(
            "Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests"
        )

    organization_id = f"mock-rag-test-{uuid4().hex}"
    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    mandatory = Standard(
        standard_id="MOCK-RAG-MANDATORY",
        version="1",
        title="Do not silently swallow exceptions",
        guidance="Handle exceptions explicitly.",
        source="integration-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )
    related = Standard(
        standard_id="MOCK-RAG-CANCELLATION",
        version="1",
        title="Pass cancellation tokens",
        guidance="Propagate cancellation tokens to asynchronous calls.",
        source="integration-test",
        enforcement=Enforcement.RECOMMENDED,
        language="csharp",
        category="reliability",
        severity=Severity.MEDIUM,
    )

    class FakeEmbedder:
        model = "deterministic-test-embedder"
        dimensions = 1536

        async def embed(
            self,
            texts: tuple[str, ...],
        ) -> tuple[tuple[float, ...], ...]:
            vectors = []
            for text in texts:
                if "cancellation" in text.casefold():
                    vectors.append((1.0,) + (0.0,) * 1535)
                else:
                    vectors.append((0.0, 1.0) + (0.0,) * 1534)
            return tuple(vectors)

    async def verify_mock_rag() -> None:
        try:
            await SqlAlchemyStandardsWriter(session_factory).add_many(
                organization_id,
                (mandatory, related),
            )

            store = SqlAlchemyStandardEmbeddingStore(session_factory)
            embedder = FakeEmbedder()

            indexed_count = await IndexStandards(store, embedder).execute(
                organization_id
            )
            assert indexed_count == 2

            results = await RetrieveRelevantStandards(
                store,
                embedder,
            ).execute(
                ReviewRun(
                    organization_id,
                    "test-repository",
                    1,
                    "test-revision",
                ),
                (
                    ChangedFile(
                        "src/example.cs",
                        ChangeKind.MODIFIED,
                        1,
                        0,
                        patch=(
                            "@@ -1 +1 @@\n"
                            "-DoWork();\n"
                            "+DoWork(cancellationToken);\n"
                        ),
                    ),
                ),
            )

            assert {standard.standard_id for standard in results} == {
                "MOCK-RAG-MANDATORY",
                "MOCK-RAG-CANCELLATION",
            }
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify_mock_rag(), loop_factory=asyncio.SelectorEventLoop)