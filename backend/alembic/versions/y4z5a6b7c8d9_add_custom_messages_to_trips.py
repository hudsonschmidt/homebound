"""Add custom message columns to trips table

Adds custom_start_message and custom_overdue_message for premium users
to personalize notifications to their contacts.

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-01-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'y4z5a6b7c8d9'
down_revision: Union[str, None] = 'x3y4z5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add custom message columns to trips table."""
    op.add_column('trips',
                  sa.Column('custom_start_message', sa.Text(), nullable=True))
    op.add_column('trips',
                  sa.Column('custom_overdue_message', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove custom message columns from trips table."""
    op.drop_column('trips', 'custom_overdue_message')
    op.drop_column('trips', 'custom_start_message')
