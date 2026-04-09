"""add multi-tenancy: users table, user_id on api_keys and collections

Revision ID: a1b2c3d4e5f6
Revises: 328772315c33
Create Date: 2026-04-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '328772315c33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add users table, user_id to api_keys and collections."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)

    # 1. Create users table
    if 'users' not in inspector.get_table_names():
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(), nullable=False),
            sa.Column('password_hash', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_users_id', 'users', ['id'])
        op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. Add user_id to api_keys
    api_key_cols = [c['name'] for c in inspector.get_columns('api_keys')]
    if 'user_id' not in api_key_cols:
        with op.batch_alter_table('api_keys', schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_index('ix_api_keys_user_id', ['user_id'])

    # 3. Add user_id to collections
    collection_cols = [c['name'] for c in inspector.get_columns('collections')]
    if 'user_id' not in collection_cols:
        with op.batch_alter_table('collections', schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
            batch_op.create_index('ix_collections_user_id', ['user_id'])


def downgrade() -> None:
    """Remove multi-tenancy columns and users table."""
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)

    # Remove user_id from collections
    collection_cols = [c['name'] for c in inspector.get_columns('collections')]
    if 'user_id' in collection_cols:
        with op.batch_alter_table('collections', schema=None) as batch_op:
            batch_op.drop_index('ix_collections_user_id')
            batch_op.drop_column('user_id')

    # Remove user_id from api_keys
    api_key_cols = [c['name'] for c in inspector.get_columns('api_keys')]
    if 'user_id' in api_key_cols:
        with op.batch_alter_table('api_keys', schema=None) as batch_op:
            batch_op.drop_index('ix_api_keys_user_id')
            batch_op.drop_column('user_id')

    # Drop users table
    if 'users' in inspector.get_table_names():
        op.drop_index('ix_users_email', table_name='users')
        op.drop_index('ix_users_id', table_name='users')
        op.drop_table('users')
