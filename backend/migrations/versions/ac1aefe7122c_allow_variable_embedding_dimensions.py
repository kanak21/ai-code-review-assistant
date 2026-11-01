"""allow variable embedding dimensions

Revision ID: ac1aefe7122c
Revises: 54bf9b381693
Create Date: 2026-10-31 21:35:51.976338

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac1aefe7122c'
down_revision: Union[str, Sequence[str], None] = '54bf9b381693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TABLE standard_embeddings "
        "ALTER COLUMN embedding TYPE vector "
        "USING embedding::vector"
    )


def downgrade() -> None:
    """Downgrade schema."""
    has_non_1536_vectors = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS ("
            "SELECT 1 FROM standard_embeddings "
            "WHERE vector_dims(embedding) <> 1536"
            ")"
        )
    ).scalar_one()

    if has_non_1536_vectors:
        raise RuntimeError(
            "Cannot downgrade: standard embeddings include non-1536-dimensional vectors"
        )

    op.execute(
        "ALTER TABLE standard_embeddings "
        "ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
