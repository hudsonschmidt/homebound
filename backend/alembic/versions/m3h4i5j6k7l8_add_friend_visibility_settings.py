"""Add friend visibility settings to users

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2025-12-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm3h4i5j6k7l8'
down_revision: Union[str, None] = 'l2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add friend visibility settings columns to users table."""
    # These settings control what friends (app users who are safety contacts) can see
    # By default, friends get richer information than email contacts
    op.add_column('users', sa.Column('friend_share_checkin_locations', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('friend_share_live_location', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('friend_share_notes', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('friend_allow_update_requests', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Remove friend visibility settings columns from users table."""
    op.drop_column('users', 'friend_allow_update_requests')
    op.drop_column('users', 'friend_share_notes')
    op.drop_column('users', 'friend_share_live_location')
    op.drop_column('users', 'friend_share_checkin_locations')
