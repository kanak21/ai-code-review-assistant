from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from code_review_assistant.infrastructure.database.base import Base


class GitHubInstallationRecord(Base):
    __tablename__ = "github_installations"
    __table_args__ = (
        UniqueConstraint("installation_id", name="uq_github_installations_installation_id"),
        CheckConstraint("installation_id > 0", name="installation_id_positive"),
    )

    organization_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )