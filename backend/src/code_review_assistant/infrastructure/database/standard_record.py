from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from code_review_assistant.infrastructure.database.base import Base


class StandardRecord(Base):
    __tablename__ = "standards"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "standard_id",
            "version",
            name="uq_standards_org_rule_version",
        ),
        CheckConstraint(
            "enforcement IN ('mandatory', 'recommended')",
            name="enforcement",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="severity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(1000), nullable=False)
    enforcement: Mapped[str] = mapped_column(String(20), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )