from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from code_review_assistant.infrastructure.database.base import Base


class ReviewRecord(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_reviews_job_id"),
        CheckConstraint("changed_files >= 0", name="changed_files_nonnegative"),
        CheckConstraint("analyzed_files >= 0", name="analyzed_files_nonnegative"),
        CheckConstraint(
            "analyzed_files <= changed_files",
            name="analyzed_files_within_changed_files",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("review_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    changed_files: Mapped[int] = mapped_column(Integer, nullable=False)
    analyzed_files: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )