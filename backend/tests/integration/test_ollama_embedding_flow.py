import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from code_review_assistant.application.services.index_standards import IndexStandards
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
from code_review_assistant.infrastructure.llm.ollama_text_embedder import (
    OllamaTextEmbedder,
)
from code_review_assistant.settings import Settings


@pytest.mark.integration
def test_ollama_embeddings_index_and_search_in_postgres() -> None:
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL tests")
    if os.getenv("RUN_OLLAMA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_OLLAMA_INTEGRATION_TESTS=1 to call local Ollama")

    organization_id = f"ollama-embedding-{uuid4().hex}"
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
    dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

    settings = Settings().model_copy(
        update={"postgres_db": "review_assistant_test"}
    )
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    standard = Standard(
        standard_id=f"OLLAMA-{uuid4().hex[:12]}",
        version="1",
        title="Avoid blocking asynchronous code",
        guidance="Do not synchronously block on a Task.",
        source="ollama-integration-test",
        enforcement=Enforcement.MANDATORY,
        language="csharp",
        category="reliability",
        severity=Severity.HIGH,
    )

    async def verify() -> None:
        try:
            await SqlAlchemyStandardsWriter(session_factory).add_many(
                organization_id,
                (standard,),
            )
            store = SqlAlchemyStandardEmbeddingStore(session_factory)

            async with httpx.AsyncClient(timeout=180.0) as client:
                embedder = OllamaTextEmbedder(
                    client,
                    base_url,
                    model,
                    dimensions,
                )

                indexed_count = await IndexStandards(
                    store,
                    embedder,
                ).execute(organization_id)
                assert indexed_count == 1

                document = (await store.list_active_standards(organization_id))[0]
                (query_vector,) = await embedder.embed((document.text,))

                results = await store.find_similar_standards(
                    organization_id=organization_id,
                    language="csharp",
                    embedding_model=model,
                    query_vector=query_vector,
                    limit=1,
                )

            assert results
            assert results[0].standard_id == standard.standard_id

            async with session_factory() as session:
                persisted = await session.scalar(
                    select(StandardEmbeddingRecord.embedding).where(
                        StandardEmbeddingRecord.embedding_model == model,
                        StandardEmbeddingRecord.standard_record_id
                        == document.standard_record_id,
                    )
                )

            assert persisted is not None
            assert len(persisted) == dimensions
        finally:
            async with session_factory.begin() as session:
                await session.execute(
                    delete(StandardRecord).where(
                        StandardRecord.organization_id == organization_id
                    )
                )
            await engine.dispose()

    asyncio.run(verify(), loop_factory=asyncio.SelectorEventLoop)