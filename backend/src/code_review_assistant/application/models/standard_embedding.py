from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StandardEmbeddingDocument:
    standard_record_id: int
    standard_id: str
    version: str
    title: str
    guidance: str
    source: str
    language: str
    category: str

    @property
    def text(self) -> str:
        return "\n".join(
            (
                f"Standard: {self.standard_id} (version {self.version})",
                f"Language: {self.language}",
                f"Category: {self.category}",
                f"Title: {self.title}",
                f"Guidance: {self.guidance}",
                f"Source: {self.source}",
            )
        )


@dataclass(frozen=True, slots=True)
class StandardEmbedding:
    standard_record_id: int
    content_hash: str
    vector: tuple[float, ...]