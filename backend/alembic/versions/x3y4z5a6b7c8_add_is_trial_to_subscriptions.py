"""Add is_trial column to subscriptions table

Adds trial status tracking for subscription purchases.

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-01-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'x3y4z5a6b7c8'
down_revision: Union[str, None] = 'w2x3y4z5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_trial column to subscriptions table."""
    op.add_column('subscriptions',
                  sa.Column('is_trial', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    """Remove is_trial column from subscriptions table."""
    op.drop_column('subscriptions', 'is_trial')
