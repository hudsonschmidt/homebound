"""Add share_location column to trip_participants

Adds a boolean column for participants to opt-in/out of sharing
their location with the group during trips.

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-01-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'z5a6b7c8d9e0'
down_revision: Union[str, None] = 'y4z5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add share_location column to trip_participants table."""
    op.add_column('trip_participants',
                  sa.Column('share_location', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Remove share_location column from trip_participants table."""
    op.drop_column('trip_participants', 'share_location')
