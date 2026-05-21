"""merge pg_vectors and user_tracking branches

Revision ID: 60fa8925e61b
Revises: 6e3b451cf943, b4e7f2a8c3d1
Create Date: 2026-04-14 10:02:43.939528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60fa8925e61b'
down_revision: Union[str, Sequence[str], None] = ('6e3b451cf943', 'b4e7f2a8c3d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
