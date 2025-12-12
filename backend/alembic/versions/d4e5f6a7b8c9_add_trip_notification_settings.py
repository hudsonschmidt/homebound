"""add_trip_notification_settings

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-12-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-trip notification settings columns."""
    # Check-in reminder interval in minutes (default 30)
    op.add_column('trips', sa.Column('checkin_interval_min', sa.Integer(), nullable=True, server_default='30'))

    # Notification active hours (0-23). NULL means no restriction.
    op.add_column('trips', sa.Column('notify_start_hour', sa.Integer(), nullable=True))
    op.add_column('trips', sa.Column('notify_end_hour', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove per-trip notification settings columns."""
    op.drop_column('trips', 'notify_end_hour')
    op.drop_column('trips', 'notify_start_hour')
    op.drop_column('trips', 'checkin_interval_min')
