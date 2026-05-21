"""add HNSW index on pg_vectors embedding column

Revision ID: b4e7f2a8c3d1
Revises: 9f3c2b7a1d10
Create Date: 2026-04-14 00:00:00.000000

Performance optimization: adds pgvector HNSW index on the embedding column
using vector_cosine_ops. This transforms search from O(n) sequential scan to
O(log n) approximate nearest neighbor.

For normalized vectors (which this app always produces), cosine distance and
inner product are equivalent, so a single cosine index serves both metrics.

NOTE: For large existing datasets (1M+ vectors), this migration may take
10-30 minutes. For zero-downtime on large tables, run manually:
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pg_vectors_embedding_hnsw
  ON pg_vectors USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4e7f2a8c3d1"
down_revision: Union[str, Sequence[str], None] = "9f3c2b7a1d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only applies to PostgreSQL with pgvector extension
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect != "postgresql":
        return

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_pg_vectors_embedding_hnsw
        ON pg_vectors USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """))


def downgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name
    if dialect != "postgresql":
        return

    op.execute(sa.text("DROP INDEX IF EXISTS idx_pg_vectors_embedding_hnsw"))
