"""Add notification tracking columns to trips

Revision ID: e1f2a3b4c5d6
Revises: fc7f7cf2e99e
Create Date: 2024-11-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = '08febd5e9e09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add notification tracking columns to trips table
    op.add_column('trips', sa.Column('notified_starting_soon', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trips', sa.Column('notified_trip_started', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trips', sa.Column('notified_approaching_eta', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trips', sa.Column('notified_eta_reached', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('trips', sa.Column('last_checkin_reminder', sa.DateTime(), nullable=True))
    op.add_column('trips', sa.Column('last_grace_warning', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('trips', 'notified_starting_soon')
    op.drop_column('trips', 'notified_trip_started')
    op.drop_column('trips', 'notified_approaching_eta')
    op.drop_column('trips', 'notified_eta_reached')
    op.drop_column('trips', 'last_checkin_reminder')
    op.drop_column('trips', 'last_grace_warning')
