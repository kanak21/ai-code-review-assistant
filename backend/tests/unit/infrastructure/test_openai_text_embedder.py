import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from code_review_assistant.infrastructure.llm.openai_text_embedder import (
    DIMENSIONS,
    MODEL,
    OpenAITextEmbedder,
)


def test_openai_embedder_sends_batch_and_restores_input_order() -> None:
    first_vector = [0.1] * DIMENSIONS
    second_vector = [0.2] * DIMENSIONS
    create = AsyncMock(
        return_value=SimpleNamespace(
            data=(
                SimpleNamespace(index=1, embedding=second_vector),
                SimpleNamespace(index=0, embedding=first_vector),
            )
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    embedder = OpenAITextEmbedder(client)

    result = asyncio.run(embedder.embed(("first text", "second text")))

    assert result == (tuple(first_vector), tuple(second_vector))
    create.assert_awaited_once_with(
        input=["first text", "second text"],
        model=MODEL,
        dimensions=DIMENSIONS,
    )


def test_openai_embedder_returns_empty_for_empty_batch_without_calling_api() -> None:
    create = AsyncMock()
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    embedder = OpenAITextEmbedder(client)

    assert asyncio.run(embedder.embed(())) == ()
    create.assert_not_awaited()