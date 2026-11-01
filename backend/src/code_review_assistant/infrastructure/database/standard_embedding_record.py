from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from code_review_assistant.infrastructure.database.base import Base


class StandardEmbeddingRecord(Base):
    __tablename__ = "standard_embeddings"

    standard_record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("standards.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )