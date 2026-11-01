from code_review_assistant.infrastructure.database.base import Base
from code_review_assistant.infrastructure.database.standard_embedding_record import (
    StandardEmbeddingRecord,
)


def test_standard_embedding_record_matches_vector_schema() -> None:
    table = Base.metadata.tables["standard_embeddings"]

    assert table is StandardEmbeddingRecord.__table__
    assert table.columns["embedding"].type.dim is None
    assert table.columns["content_hash"].type.length == 64
    assert table.columns["standard_record_id"].primary_key
    assert table.columns["embedding_model"].primary_key