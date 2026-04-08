"""add description to collections, add key_usage_logs table

Revision ID: 328772315c33
Revises: f4b4a61c7754
Create Date: 2026-04-08 09:15:47.661248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '328772315c33'
down_revision: Union[str, Sequence[str], None] = 'f4b4a61c7754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)

    # Add description to collections (guard if already exists)
    existing_cols = [c['name'] for c in inspector.get_columns('collections')]
    if 'description' not in existing_cols:
        with op.batch_alter_table('collections', schema=None) as batch_op:
            batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))

    # Create key_usage_logs table (guard if already exists)
    if 'key_usage_logs' not in inspector.get_table_names():
        op.create_table(
            'key_usage_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('key_id', sa.Integer(), nullable=True),
            sa.Column('key_name', sa.String(), nullable=False),
            sa.Column('endpoint', sa.String(), nullable=False),
            sa.Column('method', sa.String(), nullable=False),
            sa.Column('status_code', sa.Integer(), nullable=False),
            sa.Column('timestamp', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_key_usage_logs_id', 'key_usage_logs', ['id'])
        op.create_index('ix_key_usage_logs_key_id', 'key_usage_logs', ['key_id'])
        op.create_index('ix_key_usage_logs_timestamp', 'key_usage_logs', ['timestamp'])


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)

    if 'key_usage_logs' in inspector.get_table_names():
        op.drop_index('ix_key_usage_logs_timestamp', table_name='key_usage_logs')
        op.drop_index('ix_key_usage_logs_key_id', table_name='key_usage_logs')
        op.drop_index('ix_key_usage_logs_id', table_name='key_usage_logs')
        op.drop_table('key_usage_logs')

    existing_cols = [c['name'] for c in inspector.get_columns('collections')]
    if 'description' in existing_cols:
        with op.batch_alter_table('collections', schema=None) as batch_op:
            batch_op.drop_column('description')
