"""add_collection_extraction_config

Revision ID: 14e11560febc
Revises: 5a3e68f03094
Create Date: 2026-05-08 00:47:15.658923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '14e11560febc'
down_revision: Union[str, Sequence[str], None] = '5a3e68f03094'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extraction_model', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('extraction_api_keys', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('collections', schema=None) as batch_op:
        batch_op.drop_column('extraction_api_keys')
        batch_op.drop_column('extraction_model')
