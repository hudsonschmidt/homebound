"""Add last_checkin_reminder to trip_participants

Track when each participant last received a check-in reminder,
enabling individual reminder schedules per participant.

Revision ID: u1p2q3r4s5t6
Revises: t0o1p2q3r4s5
Create Date: 2026-01-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'u1p2q3r4s5t6'
down_revision: Union[str, None] = 't0o1p2q3r4s5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_checkin_reminder column to trip_participants."""
    op.add_column('trip_participants', sa.Column('last_checkin_reminder', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove last_checkin_reminder column from trip_participants."""
    op.drop_column('trip_participants', 'last_checkin_reminder')
