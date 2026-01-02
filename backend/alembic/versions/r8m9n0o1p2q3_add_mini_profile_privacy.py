"""Add mini profile privacy settings to users

Revision ID: r8m9n0o1p2q3
Revises: q7l8m9n0o1p2
Create Date: 2026-01-02

Changes:
- Add privacy settings for mini profile stats (age, total_trips, adventure_time, favorite_activity)
- These control what friends see on your mini profile, separate from trip visibility settings
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'r8m9n0o1p2q3'
down_revision: Union[str, None] = 'q7l8m9n0o1p2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add mini profile privacy settings columns to users table."""
    # These settings control what stats friends see on your mini profile
    # By default, all stats are visible to friends (backwards compatible)
    op.add_column('users', sa.Column('friend_share_age', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('friend_share_total_trips', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('friend_share_adventure_time', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('friend_share_favorite_activity', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Remove mini profile privacy settings columns from users table."""
    op.drop_column('users', 'friend_share_favorite_activity')
    op.drop_column('users', 'friend_share_adventure_time')
    op.drop_column('users', 'friend_share_total_trips')
    op.drop_column('users', 'friend_share_age')
