"""add apple_user_id to users

Revision ID: fc7f7cf2e99e
Revises: a7818caa48a6
Create Date: 2025-11-23 21:10:16.649184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fc7f7cf2e99e'
down_revision: Union[str, Sequence[str], None] = 'a7818caa48a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add apple_user_id column to users table for Sign in with Apple support."""
    op.add_column('users', sa.Column('apple_user_id', sa.Text(), nullable=True))
    op.create_unique_constraint('uq_users_apple_user_id', 'users', ['apple_user_id'])


def downgrade() -> None:
    """Remove apple_user_id column from users table."""
    op.drop_constraint('uq_users_apple_user_id', 'users', type_='unique')
    op.drop_column('users', 'apple_user_id')
