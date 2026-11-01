from typing import Protocol, Sequence

from code_review_assistant.application.ports.text_embedder import TextEmbedder


MODEL = "text-embedding-3-small"
DIMENSIONS = 1536


class _EmbeddingItem(Protocol):
    index: int
    embedding: Sequence[float]


class _EmbeddingResponse(Protocol):
    data: Sequence[_EmbeddingItem]


class _EmbeddingsResource(Protocol):
    async def create(
        self,
        *,
        input: list[str],
        model: str,
        dimensions: int,
    ) -> _EmbeddingResponse: ...


class _OpenAIClient(Protocol):
    embeddings: _EmbeddingsResource


class OpenAITextEmbedder(TextEmbedder):
    model = MODEL
    dimensions = DIMENSIONS
    def __init__(self, client: _OpenAIClient) -> None:
        self._client = client

    async def embed(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        if not isinstance(texts, tuple):
            raise ValueError("texts must be a tuple")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("texts must contain non-empty strings")
        if not texts:
            return ()

        response = await self._client.embeddings.create(
            input=list(texts),
            model=MODEL,
            dimensions=DIMENSIONS,
        )

        items = sorted(response.data, key=lambda item: item.index)
        if len(items) != len(texts) or [
            item.index for item in items
        ] != list(range(len(texts))):
            raise RuntimeError("embedding response indexes do not match inputs")

        vectors = tuple(
            tuple(float(value) for value in item.embedding)
            for item in items
        )
        if any(len(vector) != DIMENSIONS for vector in vectors):
            raise RuntimeError(
                f"embedding response vectors must have {DIMENSIONS} dimensions"
            )

        return vectors