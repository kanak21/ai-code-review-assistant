import asyncio

from code_review_assistant.application.ports.text_embedder import TextEmbedder


class FakeTextEmbedder:
    model = "test-embedding-model"
    dimensions = 2

    async def embed(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        return tuple(
            (float(index), float(index + 1))
            for index, _ in enumerate(texts)
        )


def test_text_embedder_port_accepts_provider_independent_implementation() -> None:
    embedder: TextEmbedder = FakeTextEmbedder()

    result = asyncio.run(embedder.embed(("standard text", "changed code")))

    assert result == ((0.0, 1.0), (1.0, 2.0))