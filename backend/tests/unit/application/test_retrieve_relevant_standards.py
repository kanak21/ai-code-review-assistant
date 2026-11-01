import asyncio

import pytest

from code_review_assistant.domain.models.changed_file import ChangedFile, ChangeKind
from code_review_assistant.domain.models.review_finding import Severity
from code_review_assistant.domain.models.review_run import ReviewRun
from code_review_assistant.domain.models.standard import Enforcement, Standard
from code_review_assistant.application.services.retrieve_relevant_standards import (
    RetrieveRelevantStandards,
)


def make_standard(standard_id: str, enforcement: Enforcement) -> Standard:
    return Standard(
        standard_id=standard_id,
        version="1",
        title=f"Title {standard_id}",
        guidance=f"Guidance {standard_id}",
        source="test",
        enforcement=enforcement,
        language="csharp",
        category="reliability",
        severity=Severity.MEDIUM,
    )


class FakeStore:
    def __init__(
        self,
        mandatory: tuple[Standard, ...] = (),
        similar: tuple[Standard, ...] = (),
    ) -> None:
        self.mandatory = mandatory
        self.similar = similar
        self.mandatory_call: tuple[str, str] | None = None
        self.similarity_call: dict[str, object] | None = None

    async def list_mandatory_standards(
        self,
        organization_id: str,
        language: str,
    ) -> tuple[Standard, ...]:
        self.mandatory_call = (organization_id, language)
        return self.mandatory

    async def find_similar_standards(
        self,
        organization_id: str,
        language: str,
        embedding_model: str,
        query_vector: tuple[float, ...],
        limit: int,
    ) -> tuple[Standard, ...]:
        self.similarity_call = {
            "organization_id": organization_id,
            "language": language,
            "embedding_model": embedding_model,
            "query_vector": query_vector,
            "limit": limit,
        }
        return self.similar


class FakeEmbedder:
    model = "test-embedding-model"
    dimensions = 768

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def embed(
        self,
        texts: tuple[str, ...],
    ) -> tuple[tuple[float, ...], ...]:
        self.calls.append(texts)
        return ((1.0,) + (0.0,) * 767,)


def make_file(
    path: str = "src/Example.cs",
    patch: str | None = "@@ -1 +1 @@\n-old\n+new\n",
    kind: ChangeKind = ChangeKind.MODIFIED,
) -> ChangedFile:
    return ChangedFile(
        path=path,
        kind=kind,
        additions=1,
        deletions=1,
        patch=patch,
    )


def test_retrieval_merges_mandatory_and_similar_without_duplicates() -> None:
    mandatory = make_standard("RULE-MANDATORY", Enforcement.MANDATORY)
    similar_duplicate = mandatory
    similar = make_standard("RULE-RELATED", Enforcement.RECOMMENDED)
    store = FakeStore((mandatory,), (similar_duplicate, similar))
    embedder = FakeEmbedder()
    service = RetrieveRelevantStandards(store, embedder)

    result = asyncio.run(
        service.execute(
            ReviewRun("org-1", "repo-1", 1, "revision-1"),
            (make_file(),),
        )
    )

    assert result == (mandatory, similar)
    assert store.mandatory_call == ("org-1", "csharp")
    assert store.similarity_call is not None
    assert store.similarity_call["organization_id"] == "org-1"
    assert store.similarity_call["embedding_model"] == embedder.model
    assert store.similarity_call["limit"] == 5
    assert len(embedder.calls) == 1


def test_skips_embedding_when_no_csharp_patch_is_available() -> None:
    store = FakeStore()
    embedder = FakeEmbedder()
    service = RetrieveRelevantStandards(store, embedder)

    result = asyncio.run(
        service.execute(
            ReviewRun("org-1", "repo-1", 1, "revision-1"),
            (
                make_file(path="README.md"),
                make_file(kind=ChangeKind.DELETED),
                make_file(patch=None),
            ),
        )
    )

    assert result == ()
    assert embedder.calls == []
    assert store.mandatory_call is None
    assert store.similarity_call is None


def test_rejects_oversized_diff_context() -> None:
    store = FakeStore()
    embedder = FakeEmbedder()
    service = RetrieveRelevantStandards(store, embedder)
    large_file = make_file(patch="x" * 12_001)

    with pytest.raises(ValueError, match="exceeds"):
        asyncio.run(
            service.execute(
                ReviewRun("org-1", "repo-1", 1, "revision-1"),
                (large_file,),
            )
        )

    assert embedder.calls == []