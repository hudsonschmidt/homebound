"""add_start_location_to_trips

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add start location columns to trips table for separate start/destination support."""
    op.add_column('trips', sa.Column('start_location_text', sa.Text(), nullable=True))
    op.add_column('trips', sa.Column('start_lat', sa.Float(), nullable=True))
    op.add_column('trips', sa.Column('start_lon', sa.Float(), nullable=True))
    op.add_column('trips', sa.Column('has_separate_locations', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Remove start location columns from trips table."""
    op.drop_column('trips', 'start_location_text')
    op.drop_column('trips', 'start_lat')
    op.drop_column('trips', 'start_lon')
    op.drop_column('trips', 'has_separate_locations')
