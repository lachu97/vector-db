"""add_tier_and_usage_tracking

Revision ID: 41950d991f39
Revises: a1b2c3d4e5f6
Create Date: 2026-04-09 21:15:53.975514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41950d991f39'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create user_usage_summary table
    op.create_table(
        'user_usage_summary',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('period', sa.String(), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('vector_count', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('user_id', 'period', name='uq_user_usage_period'),
    )

    with op.batch_alter_table('key_usage_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_key_usage_logs_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tier', sa.String(), nullable=False, server_default='free'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_usage_summary')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('tier')

    with op.batch_alter_table('key_usage_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_key_usage_logs_user_id'))
        batch_op.drop_column('user_id')
