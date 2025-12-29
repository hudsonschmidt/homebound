"""Add live locations table and per-trip sharing flag

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2025-12-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'n4i5j6k7l8m9'
down_revision: Union[str, None] = 'm3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create live_locations table and add share_live_location to trips."""
    # Create live_locations table for real-time tracking during trips
    op.create_table(
        'live_locations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trip_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('altitude', sa.Float(), nullable=True),
        sa.Column('horizontal_accuracy', sa.Float(), nullable=True),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['trip_id'], ['trips.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    # Index for efficient querying of latest location by trip
    op.create_index('idx_live_locations_trip_timestamp', 'live_locations', ['trip_id', 'timestamp'])

    # Add per-trip opt-in for live location sharing
    op.add_column('trips', sa.Column('share_live_location', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    """Remove live_locations table and share_live_location from trips."""
    op.drop_column('trips', 'share_live_location')
    op.drop_index('idx_live_locations_trip_timestamp', table_name='live_locations')
    op.drop_table('live_locations')
