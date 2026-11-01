import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from code_review_assistant.infrastructure.llm.ollama_text_embedder import (
    OllamaTextEmbedder,
)


def test_ollama_embedder_posts_batch_and_returns_vectors() -> None:
    vectors = [[0.1] * 768, [0.2] * 768]
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": vectors},
    )
    post = AsyncMock(return_value=response)
    client = SimpleNamespace(post=post)
    embedder = OllamaTextEmbedder(
        client,
        "http://127.0.0.1:11434/",
        "nomic-embed-text:latest",
        768,
    )

    result = asyncio.run(embedder.embed(("first", "second")))

    assert result == (tuple(vectors[0]), tuple(vectors[1]))
    post.assert_awaited_once_with(
        "http://127.0.0.1:11434/api/embed",
        json={
            "model": "nomic-embed-text:latest",
            "input": ["first", "second"],
        },
    )


def test_ollama_embedder_rejects_wrong_dimensions() -> None:
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"embeddings": [[0.1] * 767]},
    )
    embedder = OllamaTextEmbedder(
        SimpleNamespace(post=AsyncMock(return_value=response)),
        "http://127.0.0.1:11434",
        "nomic-embed-text:latest",
        768,
    )

    with pytest.raises(RuntimeError, match="768 dimensions"):
        asyncio.run(embedder.embed(("text",)))


def test_ollama_embedder_skips_request_for_empty_input() -> None:
    post = AsyncMock()
    embedder = OllamaTextEmbedder(
        SimpleNamespace(post=post),
        "http://127.0.0.1:11434",
        "nomic-embed-text:latest",
        768,
    )

    assert asyncio.run(embedder.embed(())) == ()
    post.assert_not_awaited()