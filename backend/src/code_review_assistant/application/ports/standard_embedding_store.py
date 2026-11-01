from typing import Protocol

from code_review_assistant.application.models.standard_embedding import (
    StandardEmbedding,
    StandardEmbeddingDocument,
)
from code_review_assistant.domain.models.standard import Standard


class StandardEmbeddingStore(Protocol):
    async def list_active_standards(
        self,
        organization_id: str,
    ) -> tuple[StandardEmbeddingDocument, ...]: ...

    async def get_content_hashes(
        self,
        organization_id: str,
        standard_record_ids: tuple[int, ...],
        embedding_model: str,
    ) -> dict[int, str]: ...

    async def upsert_embeddings(
        self,
        organization_id: str,
        embedding_model: str,
        embeddings: tuple[StandardEmbedding, ...],
    ) -> None: ...

    async def find_similar_standards(
        self,
        organization_id: str,
        language: str,
        embedding_model: str,
        query_vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Standard, ...]: ...

    async def list_mandatory_standards(
        self,
        organization_id: str,
        language: str,
    ) -> tuple[Standard, ...]: ...