"""add_timezone_to_trips

Revision ID: 08febd5e9e09
Revises: d8f2a1b3c4e5
Create Date: 2025-11-27 10:30:18.342900

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08febd5e9e09'
down_revision: Union[str, Sequence[str], None] = 'd8f2a1b3c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timezone column to trips table."""
    op.add_column('trips', sa.Column('timezone', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove timezone column from trips table."""
    op.drop_column('trips', 'timezone')
