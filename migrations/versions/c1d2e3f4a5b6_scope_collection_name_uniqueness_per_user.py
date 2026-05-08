"""scope_collection_name_uniqueness_per_user

Revision ID: c1d2e3f4a5b6
Revises: 14e11560febc
Create Date: 2026-05-08 12:00:00.000000

Replace the global UNIQUE index on collections.name with a per-user
composite unique constraint UNIQUE(user_id, name).  This allows different
users to own collections that share the same name while still preventing
a single user from creating two collections with the same name.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '14e11560febc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table rebuilds the SQLite table from scratch, which lets us:
    #   1. Drop the old unique index on name alone.
    #   2. Re-add name as a plain (non-unique) index.
    #   3. Add the new named composite unique constraint (user_id, name).
    # Any pre-existing sqlite_autoindex_collections_* auto-index is also
    # replaced during the table rebuild, so we end up with exactly the
    # constraint set we want.
    with op.batch_alter_table('collections', schema=None) as batch_op:
        # Drop the old global unique index on name
        batch_op.drop_index('ix_collections_name')
        # Recreate name index as non-unique
        batch_op.create_index('ix_collections_name', ['name'], unique=False)
        # Add the per-user composite unique constraint
        batch_op.create_unique_constraint('uq_user_collection', ['user_id', 'name'])


def downgrade() -> None:
    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_collection', type_='unique')
        batch_op.drop_index('ix_collections_name')
        batch_op.create_index('ix_collections_name', ['name'], unique=True)
