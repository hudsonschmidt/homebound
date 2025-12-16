"""add_per_time_timezone_to_trips

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2025-12-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add separate timezone columns for start time and return time."""
    op.add_column('trips', sa.Column('start_timezone', sa.Text(), nullable=True))
    op.add_column('trips', sa.Column('eta_timezone', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove per-time timezone columns from trips table."""
    op.drop_column('trips', 'start_timezone')
    op.drop_column('trips', 'eta_timezone')
