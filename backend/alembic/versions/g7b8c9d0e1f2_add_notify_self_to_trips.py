"""add_notify_self_to_trips

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2025-12-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add notify_self column to trips table."""
    op.add_column('trips', sa.Column('notify_self', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Remove notify_self column from trips table."""
    op.drop_column('trips', 'notify_self')
