"""add pg_vectors shared table and collection uniqueness

Revision ID: 9f3c2b7a1d10
Revises: a1b2c3d4e5f6
Create Date: 2026-04-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector as PgVector
except Exception:  # pragma: no cover
    PgVector = sa.Text


# revision identifiers, used by Alembic.
revision: str = "9f3c2b7a1d10"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_unique(inspector, table_name: str, uq_name: str) -> bool:
    return any(uq.get("name") == uq_name for uq in inspector.get_unique_constraints(table_name))


def _has_index(inspector, table_name: str, idx_name: str) -> bool:
    return any(ix.get("name") == idx_name for ix in inspector.get_indexes(table_name))


def upgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "pg_vectors" not in tables:
        op.create_table(
            "pg_vectors",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("collection_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("external_id", sa.String(), nullable=False),
            sa.Column("embedding", PgVector(1536), nullable=False),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("collection_id", "external_id", name="uq_collection_external_id"),
        )

    inspector = inspect(bind)
    if "pg_vectors" in inspector.get_table_names():
        if not _has_index(inspector, "pg_vectors", "idx_pg_vectors_collection_id"):
            op.create_index("idx_pg_vectors_collection_id", "pg_vectors", ["collection_id"], unique=False)
        if not _has_index(inspector, "pg_vectors", "idx_pg_vectors_user_id"):
            op.create_index("idx_pg_vectors_user_id", "pg_vectors", ["user_id"], unique=False)
        if not _has_index(inspector, "pg_vectors", "idx_pg_vectors_collection_user"):
            op.create_index("idx_pg_vectors_collection_user", "pg_vectors", ["collection_id", "user_id"], unique=False)

    inspector = inspect(bind)
    if "pg_collections" in inspector.get_table_names() and not _has_unique(inspector, "pg_collections", "uq_user_collection"):
        with op.batch_alter_table("pg_collections", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_user_collection", ["user_id", "name"])

    inspector = inspect(bind)
    if "collections" in inspector.get_table_names() and not _has_unique(inspector, "collections", "uq_user_collection"):
        with op.batch_alter_table("collections", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_user_collection", ["user_id", "name"])


def downgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)

    if "collections" in inspector.get_table_names() and _has_unique(inspector, "collections", "uq_user_collection"):
        with op.batch_alter_table("collections", schema=None) as batch_op:
            batch_op.drop_constraint("uq_user_collection", type_="unique")

    inspector = inspect(bind)
    if "pg_collections" in inspector.get_table_names() and _has_unique(inspector, "pg_collections", "uq_user_collection"):
        with op.batch_alter_table("pg_collections", schema=None) as batch_op:
            batch_op.drop_constraint("uq_user_collection", type_="unique")

    inspector = inspect(bind)
    if "pg_vectors" in inspector.get_table_names():
        for idx in ("idx_pg_vectors_collection_user", "idx_pg_vectors_user_id", "idx_pg_vectors_collection_id"):
            if _has_index(inspector, "pg_vectors", idx):
                op.drop_index(idx, table_name="pg_vectors")
        op.drop_table("pg_vectors")
