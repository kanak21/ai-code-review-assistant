import math

import httpx

from code_review_assistant.application.ports.text_embedder import TextEmbedder


class OllamaTextEmbedder(TextEmbedder):
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
        dimensions: int,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must not be empty")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must not be empty")
        if (
            not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or dimensions < 1
        ):
            raise ValueError("dimensions must be a positive integer")

        self._http_client = http_client
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model
        self._dimensions = dimensions

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

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

        response = await self._http_client.post(
            self._url,
            json={"model": self._model, "input": list(texts)},
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned an invalid embedding response")

        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama returned the wrong number of embeddings")

        vectors: list[tuple[float, ...]] = []
        for embedding in embeddings:
            if not isinstance(embedding, list) or len(embedding) != self._dimensions:
                raise RuntimeError(
                    f"Ollama embeddings must have {self._dimensions} dimensions"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in embedding
            ):
                raise RuntimeError("Ollama returned an invalid embedding vector")

            vectors.append(tuple(float(value) for value in embedding))

        return tuple(vectors)