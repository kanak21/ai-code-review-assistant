import hashlib
import math

from code_review_assistant.application.models.standard_embedding import (
    StandardEmbedding,
    StandardEmbeddingDocument,
)
from code_review_assistant.application.ports.standard_embedding_store import (
    StandardEmbeddingStore,
)
from code_review_assistant.application.ports.text_embedder import TextEmbedder


_BATCH_SIZE = 64


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class IndexStandards:
    def __init__(
        self,
        store: StandardEmbeddingStore,
        embedder: TextEmbedder,
    ) -> None:
        self._store = store
        self._embedder = embedder

    async def execute(self, organization_id: str) -> int:
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise ValueError("organization_id must not be empty")

        documents = await self._store.list_active_standards(organization_id)
        if not isinstance(documents, tuple) or not all(
            isinstance(document, StandardEmbeddingDocument)
            for document in documents
        ):
            raise ValueError("store must return StandardEmbeddingDocument objects")

        record_ids = tuple(document.standard_record_id for document in documents)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("store returned duplicate standard record IDs")

        if not documents:
            return 0

        existing_hashes = await self._store.get_content_hashes(
            organization_id,
            record_ids,
            self._embedder.model,
        )

        pending = tuple(
            (document, _content_hash(document.text))
            for document in documents
            if existing_hashes.get(document.standard_record_id)
            != _content_hash(document.text)
        )

        indexed_count = 0
        for offset in range(0, len(pending), _BATCH_SIZE):
            batch = pending[offset : offset + _BATCH_SIZE]
            vectors = await self._embedder.embed(
                tuple(document.text for document, _ in batch)
            )

            if len(vectors) != len(batch):
                raise RuntimeError("embedder returned the wrong number of vectors")

            embeddings = []
            for (document, content_hash), vector in zip(batch, vectors):
                if len(vector) != self._embedder.dimensions or not all(
                    math.isfinite(value) for value in vector
                ):
                    raise RuntimeError("embedder returned an invalid vector")

                embeddings.append(
                    StandardEmbedding(
                        standard_record_id=document.standard_record_id,
                        content_hash=content_hash,
                        vector=vector,
                    )
                )

            await self._store.upsert_embeddings(
                organization_id,
                self._embedder.model,
                tuple(embeddings),
            )
            indexed_count += len(embeddings)

        return indexed_count