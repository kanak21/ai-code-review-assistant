import math

from code_review_assistant.application.ports.standard_embedding_store import (
    StandardEmbeddingStore,
)
from code_review_assistant.application.ports.text_embedder import TextEmbedder
from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Standard


_LANGUAGE = "csharp"
_MAX_QUERY_CHARACTERS = 12_000
_SEMANTIC_RESULT_LIMIT = 5


class RetrieveRelevantStandards:
    def __init__(
        self,
        store: StandardEmbeddingStore,
        embedder: TextEmbedder,
    ) -> None:
        self._store = store
        self._embedder = embedder

    async def execute(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
    ) -> tuple[Standard, ...]:
        if not isinstance(run, ReviewRun):
            raise ValueError("run must be a ReviewRun")
        if not isinstance(changed_files, tuple) or not all(
            isinstance(file, ChangedFile) for file in changed_files
        ):
            raise ValueError("changed_files must be a tuple of ChangedFile objects")

        context_files = tuple(
            file
            for file in changed_files
            if file.path.casefold().endswith(".cs")
            and file.kind is not ChangeKind.DELETED
            and file.patch is not None
            and file.patch.strip()
        )
        if not context_files:
            return ()

        query_text = "\n\n".join(
            f"File: {file.path}\n{file.patch}" for file in context_files
        )
        if len(query_text) > _MAX_QUERY_CHARACTERS:
            raise ValueError(
                f"C# diff context exceeds {_MAX_QUERY_CHARACTERS} characters"
            )

        if (
            not isinstance(self._embedder.dimensions, int)
            or isinstance(self._embedder.dimensions, bool)
            or self._embedder.dimensions < 1
        ):
            raise RuntimeError("embedder dimensions must be a positive integer")

        vectors = await self._embedder.embed((query_text,))
        if len(vectors) != 1:
            raise RuntimeError("embedder must return exactly one query vector")

        query_vector = vectors[0]
        if len(query_vector) != self._embedder.dimensions or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in query_vector
        ):
            raise RuntimeError("embedder returned an invalid query vector")

        mandatory = await self._store.list_mandatory_standards(
            run.organization_id,
            _LANGUAGE,
        )
        similar = await self._store.find_similar_standards(
            organization_id=run.organization_id,
            language=_LANGUAGE,
            embedding_model=self._embedder.model,
            query_vector=query_vector,
            limit=_SEMANTIC_RESULT_LIMIT,
        )

        if not all(isinstance(item, Standard) for item in (*mandatory, *similar)):
            raise ValueError("store must return Standard objects")

        results: list[Standard] = []
        seen: set[tuple[str, str]] = set()
        for standard in (*mandatory, *similar):
            key = (standard.standard_id, standard.version)
            if key not in seen:
                results.append(standard)
                seen.add(key)

        return tuple(results)

    async def get_applicable_standards(
        self,
        run: ReviewRun,
        changed_files: tuple[ChangedFile, ...],
    ) -> tuple[Standard, ...]:
        return await self.execute(run, changed_files)