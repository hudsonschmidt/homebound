"""Add friend_share_achievements to users

Revision ID: p6k7l8m9n0o1
Revises: o5j6k7l8m9n0
Create Date: 2025-12-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p6k7l8m9n0o1'
down_revision: Union[str, None] = 'o5j6k7l8m9n0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add friend_share_achievements column to users table."""
    op.add_column('users', sa.Column('friend_share_achievements', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Remove friend_share_achievements column from users table."""
    op.drop_column('users', 'friend_share_achievements')
