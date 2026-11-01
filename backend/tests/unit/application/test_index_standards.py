import asyncio
import hashlib

import pytest

from code_review_assistant.application.models.standard_embedding import (
    StandardEmbedding,
    StandardEmbeddingDocument,
)
from code_review_assistant.application.services.index_standards import IndexStandards


def make_document(
    record_id: int = 1,
    guidance: str = "Pass cancellation tokens to asynchronous calls.",
) -> StandardEmbeddingDocument:
    return StandardEmbeddingDocument(
        standard_record_id=record_id,
        standard_id=f"DEMO-CS-{record_id:02}",
        version="1",
        title="Propagate cancellation",
        guidance=guidance,
        source="Fictional demo standards",
        language="csharp",
        category="reliability",
    )


def content_hash(document: StandardEmbeddingDocument) -> str:
    return hashlib.sha256(document.text.encode("utf-8")).hexdigest()


class FakeStore:
    def __init__(
        self,
        documents: tuple[StandardEmbeddingDocument, ...],
        hashes: dict[int, str] | None = None,
    ) -> None:
        self.documents = documents
        self.hashes = hashes or {}
        self.requested_organization_id: str | None = None
        self.requested_record_ids: tuple[int, ...] | None = None
        self.requested_model: str | None = None
        self.upsert_calls: list[tuple[str, tuple[StandardEmbedding, ...]]] = []

    async def list_active_standards(
        self,
        organization_id: str,
    ) -> tuple[StandardEmbeddingDocument, ...]:
        self.requested_organization_id = organization_id
        return self.documents

    async def get_content_hashes(
        self,
        organization_id: str,
        standard_record_ids: tuple[int, ...],
        embedding_model: str,
    ) -> dict[int, str]:
        self.requested_organization_id = organization_id
        self.requested_record_ids = standard_record_ids
        self.requested_model = embedding_model
        return self.hashes

    async def upsert_embeddings(
        self,
        organization_id: str,
        embedding_model: str,
        embeddings: tuple[StandardEmbedding, ...],
    ) -> None:
        self.upsert_calls.append((embedding_model, embeddings))


class FakeEmbedder:
    model = "test-embedding-model"
    dimensions = 3

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.received_batches: list[tuple[str, ...]] = []

    async def embed(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        self.received_batches.append(texts)
        if self.error is not None:
            raise self.error

        return tuple((0.1, 0.2, 0.3) for _ in texts)


def test_indexes_new_standards_for_requested_organization() -> None:
    documents = (make_document(1), make_document(2))
    store = FakeStore(documents)
    embedder = FakeEmbedder()

    indexed_count = asyncio.run(
        IndexStandards(store, embedder).execute("demo-org")
    )

    assert indexed_count == 2
    assert store.requested_organization_id == "demo-org"
    assert store.requested_record_ids == (1, 2)
    assert store.requested_model == embedder.model
    assert embedder.received_batches == [
        (documents[0].text, documents[1].text)
    ]

    model, embeddings = store.upsert_calls[0]
    assert model == embedder.model
    assert tuple(item.standard_record_id for item in embeddings) == (1, 2)
    assert tuple(item.content_hash for item in embeddings) == tuple(
        content_hash(document) for document in documents
    )
    assert all(item.vector == (0.1, 0.2, 0.3) for item in embeddings)


def test_skips_standards_with_current_content_hash() -> None:
    document = make_document()
    store = FakeStore(
        (document,),
        hashes={document.standard_record_id: content_hash(document)},
    )
    embedder = FakeEmbedder()

    indexed_count = asyncio.run(
        IndexStandards(store, embedder).execute("demo-org")
    )

    assert indexed_count == 0
    assert embedder.received_batches == []
    assert store.upsert_calls == []


def test_reindexes_standard_when_content_changes() -> None:
    old_document = make_document(guidance="Old guidance.")
    updated_document = make_document(guidance="Updated guidance.")
    store = FakeStore(
        (updated_document,),
        hashes={old_document.standard_record_id: content_hash(old_document)},
    )
    embedder = FakeEmbedder()

    indexed_count = asyncio.run(
        IndexStandards(store, embedder).execute("demo-org")
    )

    assert indexed_count == 1
    assert embedder.received_batches == [(updated_document.text,)]
    _, embeddings = store.upsert_calls[0]
    assert embeddings[0].content_hash == content_hash(updated_document)
    assert embeddings[0].content_hash != content_hash(old_document)


def test_surfaces_embedding_failure_without_upserting() -> None:
    store = FakeStore((make_document(),))
    embedder = FakeEmbedder(RuntimeError("embedding provider unavailable"))

    with pytest.raises(RuntimeError, match="embedding provider unavailable"):
        asyncio.run(IndexStandards(store, embedder).execute("demo-org"))

    assert store.upsert_calls == []