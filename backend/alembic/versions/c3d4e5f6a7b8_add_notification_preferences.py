"""Add notification preference columns to users table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-12-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add notification preference columns to users table."""
    op.add_column('users', sa.Column('notify_trip_reminders', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('notify_checkin_alerts', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Remove notification preference columns from users table."""
    op.drop_column('users', 'notify_checkin_alerts')
    op.drop_column('users', 'notify_trip_reminders')
