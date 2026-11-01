"""add standard embeddings

Revision ID: 5aa5af436359
Revises: 059608711dce
Create Date: 2026-10-31 08:15:55.761002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '5aa5af436359'
down_revision: Union[str, Sequence[str], None] = '059608711dce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "standard_embeddings",
        sa.Column(
            "standard_record_id",
            sa.Integer(),
            sa.ForeignKey("standards.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=100),
            primary_key=True,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("standard_embeddings")
